# FinBoss - 企业财务AI信息化系统

> Phase 2: AI 能力验证 - Ollama 本地 LLM + RAG 知识库 + NL 查询 POC

## 快速开始

### 前置要求
- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+

### 启动基础设施

```bash
# 启动所有组件（包括 Phase 2 AI 服务）
docker-compose -f config/docker-compose.yml up -d

# 检查组件状态
docker ps | grep finboss
```

### 拉取 AI 模型（首次运行）

```bash
# Ollama 模型（Qwen2.5-7B + nomic-embed-text）
docker exec finboss-ollama ollama pull qwen2.5:7b
docker exec finboss-ollama ollama pull nomic-embed-text
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入金蝶数据库连接信息
# Phase 2 新增：OLLAMA_*, MILVUS_* 配置
```

### 初始化财务知识库

```bash
uv run python scripts/ingest_financial_knowledge.py
```

### 启动 API 服务

```bash
uv sync
uv run uvicorn api.main:app --reload --port 8000
```

### 运行测试

```bash
# 所有测试
uv run pytest tests/ -v --cov=services --cov=api

# 仅单元测试
uv run pytest tests/unit/ -v

# 仅集成测试
uv run pytest tests/integration/ -v
```

## 项目结构

```
finBoss/
├── config/          # 基础设施配置 (Docker, SeaTunnel, Flink, dbt)
├── connectors/      # 数据源连接器 (金蝶, 银行等)
├── schemas/         # Pydantic 数据模型 (raw/std/dm 三层)
├── pipelines/       # 数据管道 (接入/处理/数据集市)
├── services/       # 业务服务层
│   └── ai/        # AI 服务 (Ollama, RAG, NLQuery)
├── api/            # FastAPI REST 接口
│   └── routes/     # API 路由 (ar/, query/, ai/)
├── tests/          # 测试 (unit/, integration/)
└── scripts/       # 运维脚本
```

## Phase 里程碑

### Phase 1 ✅ 核心数据层 (已完成)

- [x] Docker Compose 一键启动所有组件
- [x] ClickHouse 数据服务
- [x] FastAPI 提供 AR 查询接口
- [x] 数据质量规则

### Phase 2 ✅ AI 能力验证 (已完成)

- [x] Ollama 本地 LLM 服务 (Qwen2.5-7B)
- [x] Milvus 向量数据库
- [x] RAG 知识库（17 条财务知识）
- [x] NL 查询 POC（自然语言 → SQL → 结果 → NL 解释）
- [x] API 端点: `/api/v1/ai/*`

### Phase 3 规划中

- [ ] 飞书机器人接入
- [ ] 提示词优化
- [ ] 归因分析 POC
- [ ] 知识版本管理

## API 文档

启动服务后访问:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### AR 接口

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/ar/summary` | GET | 公司级 AR 汇总 |
| `/api/v1/ar/customer` | GET | 客户级 AR 指标 |
| `/api/v1/ar/detail` | GET | AR 明细查询 |
| `/api/v1/ar/quality-check` | POST | 数据质量检查 |

### 数据查询接口

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/query/execute` | POST | 执行只读 SQL |
| `/api/v1/query/tables` | GET | 列出可用表 |

### AI 接口

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/ai/query` | POST | 自然语言查询 |
| `/api/v1/ai/health` | GET | AI 服务健康检查 |
| `/api/v1/ai/rag/ingest` | POST | 添加知识文档 |
| `/api/v1/ai/rag/ingest/batch` | POST | 批量添加文档 |
| `/api/v1/ai/rag/search` | GET | 知识库检索 |

### AI 查询示例

```bash
# 自然语言查询
curl -X POST "http://localhost:8000/api/v1/ai/query?question=本月应收总额是多少"

# 知识库检索
curl "http://localhost:8000/api/v1/ai/rag/search?query=逾期率如何计算&top_k=3"

# AI 健康检查
curl "http://localhost:8000/api/v1/ai/health"
```

## 文档

- [系统设计](./docs/superpowers/specs/2026-03-19-finboss-design.md)
- [实施计划](./docs/superpowers/specs/2026-03-19-finboss-implementation-plan.md)
- [Phase 1 测试报告](./docs/TEST_REPORT.md)
- [Phase 2 测试报告](./docs/TEST_REPORT_PHASE2.md)
- [Phase 2 实施计划](./docs/superpowers/plans/2026-03-20-finboss-phase2-plan.md)
