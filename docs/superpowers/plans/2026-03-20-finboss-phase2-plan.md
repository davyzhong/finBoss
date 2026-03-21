# FinBoss Phase 2 - AI 能力验证

> 版本：v1.0
> 日期：2026-03-20
> 状态：进行中

---

## 一、目标概述

Phase 2 目标是验证 AI 能力（POC），建立本地 LLM + RAG 知识库基础设施，实现自然语言查询功能。

**Phase 2 完成标准**：
- [ ] Ollama 本地 LLM 服务运行正常
- [ ] Milvus 向量数据库 + 财务知识库就绪
- [ ] NL 查询 POC 可用（"本月应收总额是多少" → 返回正确数字）
- [ ] 简单归因分析 POC 可用

---

## 二、已完成的工作

### 2.1 基础设施

- [x] **Milvus 向量数据库** - Docker Compose 中添加（etcd + milvus）
- [x] **Ollama LLM 服务** - Docker Compose 中添加
- [x] **配置文件** - `OllamaConfig` + `MilvusConfig` 添加到 `api/config.py`
- [x] **环境变量** - `.env.example` 添加 OLLAMA_*/MILVUS_* 变量
- [x] **Python 依赖** - `pymilvus`, `sentence-transformers`, `torch` 添加到 `pyproject.toml`

### 2.2 AI 服务层

- [x] **`services/ai/ollama_service.py`** - Ollama API 封装
  - `generate()` - 文本生成
  - `is_available()` - 健康检查
  - `list_models()` - 列出可用模型

- [x] **`services/ai/rag_service.py`** - RAG 知识库服务
  - `connect()` / `create_collection()` - 初始化
  - `ingest()` / `ingest_batch()` - 文档写入
  - `search()` - 向量检索
  - `is_available()` - 健康检查
  - `_generate_embedding()` - Ollama embedding API + fallback

- [x] **`services/ai/nl_query_service.py`** - NL 查询服务
  - `query()` - NL → RAG → LLM(SQL) → ClickHouse → LLM(NL解释)
  - `_extract_sql()` - 从 LLM 响应解析 SQL
  - `_validate_sql()` - SQL 安全验证
  - `health_check()` - 检查 Ollama + Milvus

### 2.3 API 路由

- [x] **`api/routes/ai.py`** - AI 端点
  - `POST /api/v1/ai/query` - 自然语言查询
  - `GET /api/v1/ai/health` - AI 服务状态
  - `POST /api/v1/ai/rag/ingest` - 添加文档
  - `POST /api/v1/ai/rag/ingest/batch` - 批量添加
  - `GET /api/v1/ai/rag/search` - 知识库检索

### 2.4 财务知识库

- [x] **`scripts/ingest_financial_knowledge.py`** - 知识初始化脚本
  - 17 条初始知识（5 财务科目 + 6 指标定义 + 6 业务规则）
  - 成功导入 Milvus

---

## 三、待完成的工作

### 3.1 Ollama 模型下载

```bash
# 检查状态
docker exec finboss-ollama ollama list

# 手动下载（如需）
docker exec finboss-ollama ollama pull qwen2.5:7b
docker exec finboss-ollama ollama pull nomic-embed-text
```

### 3.2 NL 查询 POC 验证

NL 查询流程：
```
用户: "本月应收总额是多少"
  → Ollama (generate SQL)
  → ClickHouse (execute)
  → Ollama (explain result)
  → 用户: "本月应收总额为 1395 万元..."
```

**待验证**：
- [ ] "本月应收总额是多少" → 返回正确数字
- [ ] "哪些客户逾期了" → 返回逾期客户列表
- [ ] 响应时间 < 5秒

### 3.3 归因分析 POC

**待实现**：
- [ ] 逾期率异动归因：输入"为什么本月逾期率上升了" → 给出 Top 3 原因
- [ ] 收入下降归因：输入"为什么收入下降了" → 给出维度拆解

---

## 四、技术细节

### 4.1 Ollama 配置

| 配置项 | 值 |
|--------|-----|
| 默认模型 | qwen2.5:7b |
| Embedding 模型 | nomic-embed-text |
| 温度 | 0.1 |
| 最大 Token | 512 |
| 超时 | 120 秒 |

### 4.2 Milvus 配置

| 配置项 | 值 |
|--------|-----|
| GRPC 端口 | 19530 |
| 集合名 | finboss_knowledge |
| 向量维度 | 384 |
| 索引类型 | IVF_FLAT |
| 度量类型 | L2 |

### 4.3 NL 查询提示词

**系统提示词**包含：
- ClickHouse 数据库架构（dm.dm_ar_summary, dm.dm_customer_ar, std.std_ar）
- SQL 生成规则（只允许 SELECT）
- 输出格式（JSON 包含 sql + explanation）

---

## 五、已知限制

1. **Embedding 质量**：当前使用 Ollama nomic-embed-text API，但若服务未就绪则使用假向量（仅用于 POC 演示）
2. **假向量问题**：Fallback fake embedding 仅适用于开发测试，生产必须使用真实 embedding
3. **模型大小**：Qwen2.5-7B 需要 ~4.7GB 内存，首次下载较慢
4. **SQL 解析**：LLM 返回的 SQL 解析依赖正则匹配，可能需要针对不同模型输出格式调整

---

## 六、后续计划（Phase 3）

| 任务 | 说明 |
|------|------|
| 飞书机器人接入 | 在飞书中与 AI 交互 |
| 提示词优化 | 针对财务场景优化 prompt |
| Embedding 服务化 | 独立的 embedding 微服务 |
| 知识版本管理 | 支持知识库的增删改 |
| 归因分析扩展 | 多因素归因 + 因果推断 |

---

*Phase 2 版本：v1.0*
