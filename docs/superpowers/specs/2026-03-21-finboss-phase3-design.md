# FinBoss Phase 3 - 企业集成与增强

> 版本：v1.0
> 日期：2026-03-21
> 状态：待评审

---

## 一、目标概述

Phase 3 在 Phase 2 AI 能力验证（POC）的基础上，实现企业级集成（飞书机器人）、AI 能力增强（归因分析、提示词优化）和知识库管理（完整 CRUD + 版本控制）。

**Phase 3 完成标准**：
- [ ] 飞书机器人支持消息 + 卡片交互
- [ ] 归因分析覆盖客户 × 产品 × 时间三个维度
- [ ] 提示词针对财务场景优化（含 few-shot examples）
- [ ] 知识库支持完整 CRUD + 版本历史 + 回滚

---

## 二、总体架构

```
┌─────────────────────────────────────────────────────────┐
│                     飞书客户端                           │
│  (用户 @机器人 → 接收卡片消息 → 点击按钮交互)              │
└──────────────────────┬──────────────────────────────────┘
                       │ Lark Open Platform 事件推送
                       ▼
┌─────────────────────────────────────────────────────────┐
│              feishu_bot_service (新增)                   │
│  ├── feishu_client.py    - Lark SDK 封装                │
│  ├── card_builder.py     - 交互卡片构建                  │
│  └── webhook_handler.py  - 事件处理分发                  │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  NLQueryService │  │AttributionService│  │KnowledgeManager │
│   (Phase 2)     │  │    (新增)        │  │    (新增)        │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────────────────┴────────────────────┘
                               │
                               ▼
              ┌─────────────────────────────────┐
              │        Ollama LLM Service        │
              └─────────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
  ┌─────────────┐      ┌─────────────┐       ┌─────────────┐
  │   Milvus    │      │ ClickHouse   │       │   RAG       │
  │ (知识库)     │      │  (数据)      │       │ (Phase 2)   │
  └─────────────┘      └─────────────┘       └─────────────┘
```

---

## 三、模块一：飞书机器人

### 3.1 技术选型

**Lark Open Platform SDK**: `lark-oapi` (官方 Python SDK)

**交互模式**: 消息 + 卡片（Interactive Card）

**事件订阅**：
- `im.message.receive_v1` - 接收用户消息
- 事件订阅通过企业内应用 Webhook 模式

### 3.2 核心组件

```
services/feishu/
├── __init__.py
├── feishu_client.py     # Lark SDK 封装（消息发送、卡片推送）
├── card_builder.py      # 卡片模板构建器
├── event_handler.py     # 事件分发器
└── config.py            # 飞书应用配置

api/routes/
└── feishu.py            # Webhook 端点: POST /api/v1/feishu/events
```

### 3.3 飞书客户端 (feishu_client.py)

```python
class FeishuClient:
    """飞书 SDK 封装"""

    def __init__(self, app_id: str, app_secret: str):
        self.client = lark.Client(app_id=app_id, app_secret=app_secret)

    def send_message(self, receive_id: str, msg_type: str, content: dict) -> bool:
        """发送消息"""

    def send_card(self, receive_id: str, card_content: dict) -> bool:
        """发送卡片消息"""

    def reply_message(self, message_id: str, msg_type: str, content: dict) -> bool:
        """回复消息"""

    def get_user_info(self, user_id: str) -> dict:
        """获取用户信息"""
```

### 3.4 卡片构建器 (card_builder.py)

支持以下卡片模板：

| 模板名 | 用途 | 关键元素 |
|--------|------|----------|
| `query_result_card` | NL 查询结果展示 | 数据表格、数值高亮 |
| `attribution_card` | 归因分析结果 | Top 3 原因、置信度、趋势图 |
| `summary_card` | AR 汇总报告 | KPI 卡片、对比指标 |
| `action_card` | 带按钮的交互卡 | 内联按钮、URL 链接 |

**卡片元素规范**：
- 卡片宽度: `400px` ~ `500px`
- 字体: 默认（各端兼容）
- 颜色: 主色 `#165AF5`（蓝），警示色 `#F53F3F`（红）
- 按钮: `larkmd.btn` 组件，支持回调数据

### 3.5 Webhook 端点 (api/routes/feishu.py)

```
POST /api/v1/feishu/events
```

事件验证：
- 飞书签名验证（`X-Lark-Signature` header）
- `challenge` 字段响应（URL 注册验证）

事件处理：
```python
@router.post("/events")
async def handle_feishu_event(request: Request):
    # 1. 验证签名
    # 2. 解析事件类型
    # 3. 分发到对应 Handler
    # 4. 返回 200 OK（飞书要求 3s 内响应）
```

### 3.6 消息处理流程

```
用户 @机器人 "本月应收总额"
    │
    ├─→ 飞书服务器 POST /api/v1/feishu/events
    │
    ├─→ EventHandler.dispatch()
    │       │
    │       └─→ NLQueryHandler.handle()
    │               │
    │               ├─→ NLQueryService.query("本月应收总额")
    │               │       │
    │               │       ├─→ RAGService.search()  [知识检索]
    │               │       ├─→ OllamaService.generate() [SQL生成]
    │               │       ├─→ ClickHouse.execute() [执行SQL]
    │               │       └─→ OllamaService.generate() [NL解释]
    │               │
    │               └─→ CardBuilder.build_query_result_card(result)
    │
    └─→ FeishuClient.reply_card(message_id, card)
```

### 3.7 按钮回调处理

卡片中的按钮携带 `value` 数据：
```json
{
  "action_tag": "btn_detail",
  "value": "{\"action\": \"view_detail\", \"params\": {\"type\": \"overdue\"}}"
}
```

回调处理流程：
```
用户点击按钮 → 飞书回调 POST /api/v1/feishu/events
    → 解析 action + params
    → 执行对应业务逻辑
    → 更新原卡片（edit_id）或发送新卡片
```

---

## 四、模块二：归因分析服务

### 4.1 分析维度

| 维度 | 分析内容 | 数据来源 |
|------|----------|----------|
| 客户维度 | 大客户贡献变化、新客户流失、欠款回收 | `dm.dm_customer_ar` |
| 产品维度 | 产品线销售变化、账期分布 | `std.std_ar` (需含 product_category) |
| 时间维度 | 月度环比、同比、同期对比 | `dm.dm_ar_summary` |

### 4.2 归因分析流程

```
用户: "为什么本月逾期率上升了"

Step 1: LLM 生成假设（3 个维度）
  → 假设1（客户）: "大客户账期延长导致逾期上升"
  → 假设2（产品）: "某产品线收款困难"
  → 假设3（时间）: "季度末集中结算导致"

Step 2: 并行验证假设
  → SQL_A: TOP 10 客户逾期贡献度（环比变化）
  → SQL_B: 产品线逾期分布
  → SQL_C: 月度逾期率趋势

Step 3: LLM 综合归因
  → 整合三个维度的数据
  → 输出 Top 3 归因 + 置信度 + 建议
```

### 4.3 核心组件

```
services/
├── attribution_service.py   # 归因分析逻辑
└── ai/
    └── attribution_prompts.py  # 归因分析专用提示词
```

### 4.4 AttributionService 接口

```python
class AttributionService:
    """归因分析服务"""

    def analyze(self, question: str) -> AttributionResult:
        """
        Args:
            question: 用户问题，如 "为什么本月逾期率上升了"

        Returns:
            AttributionResult:
                - hypotheses: List[Hypothesis]  # 假设列表
                - top_factors: List[Factor]     # Top 归因
                - confidence: float              # 置信度
                - suggestions: List[str]        # 建议措施
        """
```

### 4.5 归因结果数据模型

```python
class Factor(BaseModel):
    dimension: Literal["customer", "product", "time"]
    description: str           # 归因描述
    contribution: float        # 贡献度（0-1）
    evidence: dict              # 支撑数据
    confidence: float          # 置信度（0-1）
    suggestion: str             # 建议措施

class AttributionResult(BaseModel):
    question: str
    factors: List[Factor]
    overall_confidence: float
    analysis_time: float        # 分析耗时（秒）
    raw_data: dict             # 原始数据（调试用）
```

### 4.6 SQL 模板（ClickHouse）

**客户维度 - 逾期贡献度环比**：
```sql
SELECT
    customer_name,
    overdue_amount_curr,
    overdue_amount_prev,
    overdue_amount_curr - overdue_amount_prev AS overdue_delta,
    (overdue_amount_curr - overdue_amount_prev) / overdue_amount_prev AS change_rate
FROM (
    SELECT
        customer_name,
        SUM(overdue_amount) AS overdue_amount_curr
    FROM dm.dm_customer_ar
    WHERE stat_date = '{current_date}'
    GROUP BY customer_name
) CURRENT
LEFT JOIN (
    SELECT
        customer_name,
        SUM(overdue_amount) AS overdue_amount_prev
    FROM dm.dm_customer_ar
    WHERE stat_date = '{prev_date}'
    GROUP BY customer_name
) PREV ON CURRENT.customer_name = PREV.customer_name
ORDER BY overdue_delta DESC
LIMIT 10
```

**时间维度 - 月度逾期率趋势**：
```sql
SELECT
    stat_date,
    overdue_amount,
    total_ar_amount,
    overdue_rate,
    lagInFrame(overdue_rate) OVER (ORDER BY stat_date) AS prev_overdue_rate,
    overdue_rate - lagInFrame(overdue_rate) OVER (ORDER BY stat_date) AS rate_delta
FROM dm.dm_ar_summary
WHERE stat_date BETWEEN '{start_date}' AND '{end_date}'
ORDER BY stat_date
```

---

## 五、模块三：知识版本管理

### 5.1 设计目标

对 Milvus 中的知识库文档提供完整的生命周期管理，支持版本历史和回滚。

### 5.2 数据模型扩展

现有 Milvus 集合 `finboss_knowledge` 扩展字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | VARCHAR(64) | 文档ID（主键） |
| `content` | VARCHAR(4096) | 文档内容 |
| `vector` | FLOAT_VECTOR(768) | 向量 |
| `category` | VARCHAR(64) | 分类 |
| `metadata` | VARCHAR(1024) | JSON 元数据 |
| `version` | INT32 | 版本号（递增） |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |
| `is_active` | BOOL | 是否当前活跃版本 |
| `change_log` | VARCHAR(1024) | 变更说明 |

### 5.3 版本策略

- **每次 UPDATE**: 软更新（`is_active=false` 旧版本，`is_active=true` 新版本）
- **版本号**: 全局自增，每次更新 +1
- **DELETE**: 软删除（`is_active=false`），不真正删除向量数据
- **Rollback**: 将指定历史版本设为 `is_active=true`，生成新版本记录

### 5.4 核心组件

```
services/
├── knowledge_manager.py   # 知识库 CRUD + 版本管理

api/routes/
└── knowledge.py          # API 端点（替代/扩展 ai.py 中的 RAG 端点）
```

### 5.5 KnowledgeManager 接口

```python
class KnowledgeManager:
    """知识库版本管理服务"""

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
    ) -> KnowledgeListResult:
        """分页查询知识库"""

    def get(self, doc_id: str) -> KnowledgeDoc | None:
        """获取单个文档（最新活跃版本）"""

    def create(
        self,
        content: str,
        category: str = "general",
        metadata: dict | None = None,
        change_log: str = "",
    ) -> KnowledgeDoc:
        """创建文档（版本=1）"""

    def update(
        self,
        doc_id: str,
        content: str | None = None,
        category: str | None = None,
        metadata: dict | None = None,
        change_log: str = "",
    ) -> KnowledgeDoc:
        """更新文档（生成新版本）"""

    def delete(self, doc_id: str, change_log: str = "") -> bool:
        """软删除文档"""

    def get_history(self, doc_id: str) -> List[KnowledgeDoc]:
        """获取文档版本历史"""

    def rollback(self, doc_id: str, target_version: int, change_log: str = "") -> KnowledgeDoc:
        """回滚到指定版本"""
```

### 5.6 API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/ai/knowledge` | GET | 分页列表（支持 category 过滤） |
| `/api/v1/ai/knowledge` | POST | 创建文档 |
| `/api/v1/ai/knowledge/{id}` | GET | 获取文档详情 |
| `/api/v1/ai/knowledge/{id}` | PUT | 更新文档 |
| `/api/v1/ai/knowledge/{id}` | DELETE | 软删除 |
| `/api/v1/ai/knowledge/{id}/history` | GET | 版本历史 |
| `/api/v1/ai/knowledge/{id}/rollback` | POST | 回滚到指定版本 |

---

## 六、模块四：提示词优化

### 6.1 优化策略

1. **Few-shot Examples** - 在 SQL 生成 prompt 中增加 3-5 个示例问答对
2. **归因分析 Prompt** - 新增专门的归因分析 system prompt
3. **卡片格式化 Prompt** - 生成适合飞书卡片的结构化输出
4. **Prompt 版本管理** - 将 prompt 模板外部化为配置文件

### 6.2 Prompt 文件结构

```
services/ai/prompts/
├── __init__.py
├── nl_query_prompt.py     # NL 查询 prompt（含 few-shot）
├── attribution_prompt.py  # 归因分析 prompt
├── card_format_prompt.py  # 卡片文本格式化 prompt
└── result_explain_prompt.py  # 结果解释 prompt（现有）
```

### 6.3 Few-shot Examples（NL 查询）

```python
NL_QUERY_EXAMPLES = [
    {
        "question": "本月应收总额是多少",
        "sql": "SELECT SUM(total_ar_amount) AS total_ar_amount FROM dm.dm_ar_summary WHERE stat_date = 'YYYY-MM-DD'",
    },
    {
        "question": "哪些客户有逾期账款",
        "sql": "SELECT customer_name, overdue_amount FROM dm.dm_customer_ar WHERE overdue_amount > 0 ORDER BY overdue_amount DESC",
    },
    {
        "question": "C001公司的逾期率",
        "sql": "SELECT overdue_rate FROM dm.dm_ar_summary WHERE company_code = 'C001' AND stat_date = 'YYYY-MM-DD'",
    },
]
```

### 6.4 归因分析 Prompt

```python
ATTRIBUTION_SYSTEM_PROMPT = """你是一个专业的财务归因分析师。

## 你的任务
当用户询问"为什么XXX"时，你需要：
1. 生成 3 个可能的假设（客户维度、产品维度、时间维度）
2. 解释每个假设的合理性
3. 提出验证所需的 SQL 查询

## 数据库架构
{DATABASE_SCHEMA}

## 输出格式
必须返回 JSON 格式：
{
    "hypotheses": [
        {
            "dimension": "customer|product|time",
            "description": "假设描述",
            "reasoning": "为什么这个假设合理",
            "sql_template": "验证用的 SQL 模板"
        }
    ]
}
"""
```

---

## 七、飞书机器人配置

### 7.1 环境变量

```bash
# 飞书应用配置
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx
FEISHU_BOT_NAME=FinBoss财务助手

# 飞书 Webhook 验证
FEISHU_VERIFICATION_TOKEN=  # 企业内部应用可选
```

### 7.2 应用权限

| 权限名 | 权限标识 | 用途 |
|--------|----------|------|
| 获取用户信息 | contact:user.employee_id:readonly | 获取 @机器人的用户信息 |
| 发送消息 | im:message | 发送卡片消息 |
| 读取消息 | im:message:readonly | 接收用户消息 |
| 上传图片 | im:image | 卡片中嵌入图表 |

---

## 八、测试策略

### 8.1 飞书机器人测试

- **Mock 测试**: 使用 `responses` 或 `pytest-mock` Mock Lark API
- **卡片构建测试**: 验证卡片 JSON 结构符合 Lark Card 规范
- **事件分发测试**: 验证不同事件类型路由正确

### 8.2 归因分析测试

- **单元测试**: SQL 模板生成、假设生成逻辑
- **集成测试**: 端到端归因流程（Mock Ollama 输出）

### 8.3 知识管理测试

- **单元测试**: CRUD + 版本逻辑
- **集成测试**: Milvus 实际操作（使用 test container）

### 8.4 提示词测试

- **回归测试**: 用固定 query 列表验证输出格式稳定
- **格式验证**: JSON Schema 验证 LLM 输出

---

## 九、已知限制

1. **飞书应用需企业认证**: Webhook 事件订阅需要企业管理员审批
2. **卡片格式兼容**: Lark 卡片在不同端（PC/移动）的渲染略有差异
3. **归因分析置信度**: 当前为规则计算，后续可引入 ML 模型提升准确性
4. **Milvus 版本兼容性**: `pymilvus` API 可能在版本升级时变化

---

## 十、依赖关系

```
Phase 3 模块依赖

飞书机器人
  ├─→ NLQueryService (Phase 2)
  ├─→ AttributionService (Phase 3)
  └─→ FeishuClient (新增)

归因分析
  ├─→ OllamaService (Phase 2)
  ├─→ ClickHouseDataService (Phase 1)
  └─→ AttributionPrompts (新增)

知识版本管理
  └─→ RAGService (Phase 2) - 扩展

提示词优化
  ├─→ OllamaService (Phase 2)
  └─→ NLQueryService (Phase 2) - 修改
```

---

*Phase 3 版本：v1.0*
