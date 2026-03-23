# Phase 9 AI 融合助手 — 设计规格

> **日期**: 2026-03-23
> **目标**: 为 FinBoss 构建统一 AI 助手，融合 RAG 知识库检索 + 归因分析，支持多轮对话，归因结果可存为知识库案例并多维度检索

---

## 1. 目标与范围

### 核心目标
- 统一 AI 助手入口（`/api/v1/ai/copilot`）
- RAG + Attribution 多路并行，综合 LLM 生成答案
- 多轮对话记忆（ClickHouse 持久化）
- 归因结果一键存入知识库（Milvus 语义同步）
- 多维度案例检索（标签 + 语义 + 时间）
- 用户可见归因案例列表

### 本期范围
- `/api/v1/ai/copilot/*` 全部端点
- `ai_conversations` + `ai_messages` 表及 CRUD
- `attribution_cases` 表及 Milvus 同步
- CopilotService 多路并行核心逻辑
- 知识库融合（归因结果入库 + 多维检索）
- Phase 8 RBAC 数据范围控制

### 非目标
- 前端 UI（API 完成即可）
- 外部财经数据接入
- 多 Agent 协作框架

---

## 2. 架构概览

```
用户 → POST /ai/copilot/conversations/{id}/messages
              │
              ▼
       ┌─────────────────────────────┐
       │      CopilotService        │
       │  (意图判断 → 多路并行 →    │
       │   LLM 综合 → 答案+来源)   │
       └─────────────────────────────┘
              │
    ┌─────────┼──────────┐
    ▼         ▼          ▼
  RAG     Attribution  SQL Query
 Milvus   AR/AP数据   ClickHouse
    │         │          │
    └────► 结果综合 ◄────┘
              │
       ┌──────▼──────┐
       │  写 ai_messages │
       │  (存 sources/  │
       │   intent)      │
       └────────────────┘
              │
     ┌────────▼─────────┐
     │ 归因结果外露给用户 │
     │ (可点"存入知识库") │
     └──────────────────┘
              │
    ┌─────────▼─────────┐
    │ attribution_cases  │
    │ (Milvus 语义同步)  │
    └───────────────────┘
```

---

## 3. 数据模型

### ClickHouse Schema

```sql
-- AI 对话会话
CREATE TABLE IF NOT EXISTS dm.ai_conversations (
    conversation_id  String,
    user_id          String,
    role             String,
    title            String DEFAULT '',
    message_count    UInt16 DEFAULT 0,
    created_at       DateTime DEFAULT now(),
    updated_at       DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (user_id, conversation_id);

-- AI 消息历史
CREATE TABLE IF NOT EXISTS dm.ai_messages (
    message_id      String,
    conversation_id  String,
    role             String,          -- user | assistant
    content          String,
    sources          Array(String),   -- 引用来源 [RAG来源ID, 归因案例ID, SQL结果ID]
    intent           String,          -- rag | attribution | sql | mixed
    created_at       DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (conversation_id, created_at);

-- 归因案例持久化
CREATE TABLE IF NOT EXISTS dm.attribution_cases (
    case_id            String,
    conversation_id    String,
    question           String,
    answer             String,
    attribution_result String,         -- JSON 序列化归因结果
    tags               Array(String), -- 自动提取标签 [逾期, 收入, 客户A]
    milvus_doc_id      String,
    created_by         String,
    is_visible         UInt8  DEFAULT 1,
    created_at         DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (case_id, created_at);
```

### Milvus Schema

Collection: `knowledge_docs`（与现有 RAG 共用 collection）

归因案例文档格式：
```json
{
  "id": "uuid",
  "content": "问题：xxx\\n答案：xxx\\n归因因子：...\\n建议：...",
  "category": "attribution_case",
  "tags": ["逾期", "收入"],
  "created_at": "2026-03-23",
  "case_id": "uuid"
}
```

---

## 4. API 端点

### Copilot 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/ai/copilot/conversations` | 列出用户会话列表 |
| POST | `/ai/copilot/conversations` | 创建新会话 |
| GET | `/ai/copilot/conversations/{id}` | 获取会话详情（包含消息历史） |
| DELETE | `/ai/copilot/conversations/{id}` | 删除会话（仅会话所有者可删除） |
| POST | `/ai/copilot/conversations/{id}/messages` | 发送消息（多路并行处理） |

### 归因案例

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/ai/copilot/cases` | 归因案例列表（多维度检索） |
| POST | `/ai/copilot/cases/{case_id}/save-to-knowledge` | 归因结果存入知识库 |

### 请求/响应模型

**POST /conversations/{id}/messages 请求**
```json
{
  "content": "本月客户A的逾期率上升原因是什么？"
}
```

**响应**
```json
{
  "message_id": "uuid",
  "role": "assistant",
  "content": "根据分析...",
  "sources": ["milvus_doc_xxx", "case_uuid_xxx", "sql_result_xxx"],
  "intent": "mixed",
  "attribution_case": {
    "case_id": "uuid",
    "can_save": true,
    "tags": ["逾期", "客户A"]
  }
}
```

---

## 5. CopilotService 核心逻辑

### 意图判断（Intent Detection）

```python
INTENT_KEYWORDS = {
    "attribution": ["原因", "为什么", "上升", "下降", "变化", "异动", "增加", "减少"],
    "rag": ["政策", "规则", "定义", "流程", "如何"],
    "sql": ["查询", "报表", "统计", "金额", "数量", "合计"],
}

def detect_intent(content: str) -> list[str]:
    """返回触发的 intent 列表，默认返回 ['mixed']"""
    matched = []
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in content for kw in keywords):
            matched.append(intent)
    return matched or ["mixed"]
```

### 多路并行处理

```python
async def process_message(user_id: str, role: str, content: str, history: list) -> CopilotResponse:
    intents = detect_intent(content)

    tasks = {}
    # RAG 检索（几乎总是触发）
    tasks["rag"] = asyncio.create_task(rag_service.search(content, top_k=5))

    # Attribution（涉及异动/原因）
    if "attribution" in intents:
        tasks["attribution"] = asyncio.create_task(attribution_service.analyze(content, user_id, role))

    # SQL 查询（涉及数据/报表）
    if "sql" in intents:
        tasks["sql"] = asyncio.create_task(nl_query_service.query(content, user_id, role))

    results = await asyncio.gather(*tasks.values())

    # 综合 LLM 生成
    return llm_service.generate_summary(content, history, dict(zip(tasks.keys(), results)))
```

### RBAC 数据范围注入

```python
def build_sql_filter(user_id: str, role: str) -> tuple[str, dict]:
    """SQL 查询时注入数据范围过滤（参数化查询，防注入）"""
    if role == "sales_manager":
        return ("AND salesperson_id = %(salesperson_id)s", {"salesperson_id": user_id})
    return ("", {})  # finance / admin 全量
```

---

## 6. 归因案例融合逻辑

### 存入知识库流程

```
用户点击"存入知识库"
         │
         ▼
1. 提取 tags（LLM 关键词提取）
   → ["归因分析", "逾期", "客户A", "2026-03"]
         │
         ▼
2. 写入 dm.attribution_cases
         │
         ▼
3. 生成 embedding 存入 Milvus（category="attribution_case"）
         │
         ▼
4. 返回 milvus_doc_id 写入 attribution_cases 表
```

### 多维度案例检索

`GET /ai/copilot/cases` 参数：

| 参数 | 说明 |
|------|------|
| `tag` | 标签过滤（可多个，如 `?tag=逾期&tag=收入`） |
| `from` / `to` | 时间范围 |
| `q` | 语义检索（Milvus embedding similarity） |
| `page` / `page_size` | 分页 |

检索优先级：标签 + 时间过滤 → Milvus 语义排序

---

## 7. 多轮对话

### 会话历史窗口

- 每次请求拉取当前会话最近 20 条消息
- 按时间顺序组织成对话历史 prompt
- LLM prompt 结构：

```
## 对话历史
[user]: 上月逾期率上升的原因是什么？
[assistant]: (归因分析结果)
[user]: 客户A的具体情况呢？

## 当前问题
客户A的具体情况呢？

## 上下文
（检索到的知识 + 最新归因结果 + 数据摘要）
```

### 会话持久化

- 每条消息写入 `ai_messages` 表
- `sources` 字段记录引用来源（Milvus doc ID / Case ID / SQL Result ID）
- `intent` 字段记录本条消息的触发意图

---

## 8. 权限与 RBAC

- 所有 `/ai/copilot/*` 端点需要有效 session（Phase 8 SessionMiddleware）
- Phase 8 PermissionMiddleware 需更新，新增 AI 助手模块覆盖 `/ai/copilot` 路由前缀
- Phase 8 RBAC 权限矩阵扩展如下：

| 模块 | 路由前缀 | 财务 | 销售经理 | 运营 | 管理员 |
|------|----------|------|----------|------|--------|
| AI 助手 | `/ai/copilot` | 读写 | 读写 | 读写 | 读写 |

- 销售经理角色：SQL 查询自动注入 `salesperson_id` 过滤
- 归因案例：`is_visible=1` 对所有登录用户可见

---

## 9. 文件变更总览

| 文件 | 操作 |
|------|------|
| `schemas/copilot.py` | 新建 — 会话/消息/归因案例 Pydantic 模型 |
| `services/ai/copilot_service.py` | 新建 — CopilotService（意图判断/多路并行/LLM综合） |
| `services/ai/conversation_service.py` | 新建 — 会话 CRUD + 消息持久化 |
| `services/ai/case_service.py` | 新建 — 归因案例管理 + Milvus 同步 |
| `api/routes/copilot.py` | 新建 — `/ai/copilot/*` 全部端点 |
| `api/middleware/permission.py` | 修改 — 权限矩阵新增 AI 助手模块覆盖 |
| `api/main.py` | 注册 copilot_router |
| `scripts/phase9_ddl.sql` | 新建 — ai_conversations / ai_messages / attribution_cases DDL |
| `scripts/init_phase9.py` | 新建 — 幂等初始化脚本 |
| `tests/unit/test_copilot_service.py` | 新建 |
| `tests/unit/test_conversation_service.py` | 新建 |
| `tests/unit/test_case_service.py` | 新建 |
| `tests/integration/test_copilot_api.py` | 新建 |

---

## 10. 依赖关系

- `CopilotService` 依赖 `RAGService`（已有 Milvus 集成）
- `CopilotService` 依赖 `AttributionService`（已有）
- `CopilotService` 依赖 `NLQueryService`（已有）
- `CaseService` 依赖 `RAGService`（Milvus 同步）
- Phase 8 SessionMiddleware 提供用户身份和角色（前置依赖）
- ClickHouse 连接池（已有）

---

## 11. 注意事项

- 多路并行使用 `asyncio.gather`，任一路超时不阻塞其他路
- LLM 调用超时：60s；各子任务超时：30s
- Milvus 语义检索结果窗口：top_k=5
- 对话历史窗口：20 条消息，防止 prompt 溢出
- 归因案例 Milvus 同步为同步写入，失败则回滚 ClickHouse 记录
- 内存 Session 限制：Phase 8 的 in-memory session；多 worker 部署需 Redis
