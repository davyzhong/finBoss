# FinBoss Phase 3 - 企业集成与增强

> 版本：v1.0
> 日期：2026-03-21
> 状态：待评审

---

## 一、目标概述

Phase 3 在 Phase 2 AI 能力验证（POC）的基础上，实现企业级集成（飞书机器人）、AI 能力增强（归因分析、提示词优化）和知识库管理（完整 CRUD + 版本控制）。

**Phase 3 完成标准**：
- [ ] 飞书机器人支持消息 + 卡片交互
- [ ] 归因分析覆盖客户 × 时间两个维度（产品维度待数据层就绪后扩展）
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

**重要：飞书要求 Webhook 在 3 秒内响应。** 由于 LLM 推理耗时较长（10-60s），必须使用异步模式：

```
用户 @机器人 "本月应收总额"
    │
    ├─→ 飞书服务器 POST /api/v1/feishu/events
    │
    ├─→ 立即返回 200 OK（飞书要求 3s 内响应）
    │
    └─→ 后台任务（asyncio.create_task）
            │
            ├─→ NLQueryService.query("本月应收总额")
            │       ├─→ RAGService.search()
            │       ├─→ OllamaService.generate() [SQL生成]
            │       ├─→ ClickHouse.execute()
            │       └─→ OllamaService.generate() [NL解释]
            │
            ├─→ CardBuilder.build_query_result_card(result)
            │
            └─→ FeishuClient.send_card(receive_id, card)
```

**消息去重**：飞书可能重试 Webhook 推送，使用 `message_id` 做幂等去重（内存 dict 或 Redis）。

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

| 维度 | 分析内容 | 数据来源 | 状态 |
|------|----------|----------|------|
| 客户维度 | 大客户贡献变化、新客户流失、欠款回收 | `dm.dm_customer_ar` | Phase 3 实现 |
| 时间维度 | 月度环比、同比、同期对比 | `dm.dm_ar_summary` | Phase 3 实现 |
| 产品维度 | 产品线销售变化、账期分布 | `std.std_ar` (需含 product_category) | **待 Phase 4**（需扩展 Kingdee CDC pipeline 添加 product 字段） |

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
    dimension: Literal["customer", "time"]  # product 待 Phase 4
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

**置信度评分算法**（规则计算，不依赖特定 SQL 别名）：

```python
def calc_confidence(sql_result: list[dict], dimension: str) -> float:
    """
    基于 SQL 结果集质量计算置信度，不依赖具体字段名：
    - 有数据行：+0.3
    - 结果行数 > 5：+0.2
    - 最大值与平均值之比 > 3：+0.2（存在显著异常值）
    - 最大值 > 0：+0.3（有实际变化）
    最终取 min(score, 1.0)
    """
    if not sql_result:
        return 0.0

    score = 0.3  # 有数据

    if len(sql_result) > 5:
        score += 0.2

    # 取所有数值字段的最大值（通用方法）
    all_values = []
    for row in sql_result:
        for v in row.values():
            if isinstance(v, (int, float)):
                all_values.append(abs(v))

    if all_values:
        max_val = max(all_values)
        min_val = min(all_values)
        avg_val = sum(all_values) / len(all_values)
        # 有变化（不为常数集）：+0.3
        if max_val != min_val:
            score += 0.3
        # 变化幅度显著（极值/均值 > 3）：+0.2
        if avg_val != 0 and max(abs(max_val), abs(min_val)) / avg_val > 3:
            score += 0.2

    return min(score, 1.0)
```

**Overall Confidence**：各维度置信度的加权平均，客户维度权重 0.5，时间维度权重 0.5（产品维度 Phase 4 再加入）。

### 4.6 SQL 模板（ClickHouse）

**客户维度 - 逾期贡献度环比**：
（数据源：`dm.dm_customer_ar`，主键：`(stat_date, customer_code, company_code)`）

```sql
SELECT
    customer_name,
    curr.overdue_amount AS overdue_amount_curr,
    prev.overdue_amount AS overdue_amount_prev,
    curr.overdue_amount - coalesce(prev.overdue_amount, 0) AS overdue_delta,
    curr.overdue_rate AS overdue_rate_curr,
    prev.overdue_rate AS overdue_rate_prev,
    curr.total_ar_amount AS total_ar_curr,
    curr.overdue_count AS overdue_count_curr
FROM dm.dm_customer_ar curr
LEFT JOIN dm.dm_customer_ar prev
    ON curr.customer_code = prev.customer_code
    AND curr.company_code = prev.company_code
    AND prev.stat_date = toDate('{prev_date}')
WHERE curr.stat_date = toDate('{current_date}')
ORDER BY overdue_delta DESC
LIMIT 10
```

**时间维度 - 月度逾期率趋势**：
（数据源：`dm.dm_ar_summary`，主键：`(stat_date, company_code)`）

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
  AND company_code = '{company_code}'
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
| `id` | VARCHAR(64) | 文档ID（主键，Phase 2 已有） |
| `content` | VARCHAR(4096) | 文档内容（Phase 2 已有） |
| `vector` | FLOAT_VECTOR(768) | 向量（Phase 2 已有） |
| `category` | VARCHAR(64) | 分类（Phase 2 已有） |
| `metadata` | VARCHAR(1024) | JSON 元数据（Phase 2 已有） |
| `version` | INT32 | 版本号（新增，默认为 1） |
| `created_at` | DATETIME | 创建时间（新增） |
| `updated_at` | DATETIME | 更新时间（新增） |
| `is_active` | BOOL | 是否当前活跃版本（新增，默认为 True） |
| `change_log` | VARCHAR(1024) | 变更说明（新增） |

**版本号策略**：
- 全局自增，每次 CREATE 或 UPDATE 操作时 +1
- 所有历史版本保留（`is_active` 标记当前活跃版本）
- Rollback 操作生成新版本（内容来自历史版本），而非覆盖

### 5.3 集合迁移策略

**目标**：将 Phase 2 的 `finboss_knowledge` 集合迁移到含版本字段的 v2 格式，同时保证迁移过程不会丢失数据。

**核心策略**：使用 Collection Alias 实现原子切换（别名永远指向有效集合）：

```python
PRODUCTION_ALIAS = "finboss_knowledge"       # 生产别名（不变）
STAGING_NAME    = "finboss_knowledge_v2"   # 临时集合名

def migrate_collection(self, target_dimension: int = 768) -> None:
    """
    幂等迁移：Phase 2 → v2（带版本字段）
    使用 Alias 实现零停机原子切换。
    """
    # 1. 检查是否已完成迁移（幂等）
    try:
        alias = utility.get_collection_alias(PRODUCTION_ALIAS)
        if alias == STAGING_NAME:
            return  # 已迁移
    except Exception:
        pass  # 别名不存在，继续迁移

    # 2. 创建 v2 集合（含版本字段）
    self._create_versioned_collection(STAGING_NAME, dimension=target_dimension)

    # 3. 迁移 Phase 2 数据（如存在）
    try:
        old_collection = Collection("finboss_knowledge")
        old_collection.load()
        results = old_collection.query(
            expr="is_active == true || version > 0",
            output_fields=["id", "content", "vector", "category", "metadata"]
        )
        self._migrate_docs_to_v2(results)
    except Exception:
        # Phase 2 数据不存在，跳过迁移
        pass

    # 4. 原子切换别名（关键步骤）
    #    切换后，旧集合变为 "finboss_knowledge_old"，新集合变为 "finboss_knowledge"
    try:
        utility.drop_alias(PRODUCTION_ALIAS)
    except Exception:
        pass
    utility.create_alias(STAGING_NAME, PRODUCTION_ALIAS)

    # 5. 可选：删除旧集合（延迟一天，防止切回）
    # self._schedule_old_collection_cleanup("finboss_knowledge_old")
```

**别名切换语义**：别名指向的集合对应用层透明，应用始终通过别名访问集合。迁移过程中别名始终指向某个有效集合，不会出现数据不可用窗口。

**幂等保证**：迁移脚本可重复执行。每次执行会检查别名是否已指向 v2 集合，如是则直接返回。

### 5.4 版本策略

- **每次 UPDATE**: 软更新（`is_active=false` 旧版本，`is_active=true` 新版本，version +1）
- **DELETE**: 软删除（`is_active=false`），不真正删除向量数据
- **Rollback**: 将指定历史版本内容复制为新版本（version +1），保持线性历史
- **版本历史查询**: `WHERE id = '{doc_id}' ORDER BY version DESC`

### 5.5 核心组件

```
services/
├── knowledge_manager.py   # 知识库 CRUD + 版本管理

api/routes/
└── knowledge.py          # API 端点（替代/扩展 ai.py 中的 RAG 端点）
```

### 5.6 KnowledgeManager 接口

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

### 5.7 API 端点

**端点策略**：新增 `/api/v1/ai/knowledge` 端点，**与现有** `/api/v1/ai/rag/*` 端点共存，不破坏现有调用方。

| 端点 | 方法 | 描述 | 状态 |
|------|------|------|------|
| `/api/v1/ai/knowledge` | GET | 分页列表（支持 category 过滤） | 新增 |
| `/api/v1/ai/knowledge` | POST | 创建文档 | 新增 |
| `/api/v1/ai/knowledge/{id}` | GET | 获取文档详情（含当前版本） | 新增 |
| `/api/v1/ai/knowledge/{id}` | PUT | 更新文档（生成新版本） | 新增 |
| `/api/v1/ai/knowledge/{id}` | DELETE | 软删除 | 新增 |
| `/api/v1/ai/knowledge/{id}/history` | GET | 版本历史 | 新增 |
| `/api/v1/ai/knowledge/{id}/rollback` | POST | 回滚到指定版本 | 新增 |
| `/api/v1/ai/rag/ingest` | POST | 兼容 Phase 2（透传到 KnowledgeManager.create） | 现有 |
| `/api/v1/ai/rag/search` | GET | 兼容 Phase 2（仅搜 is_active=true 的文档） | 现有 |

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
        "sql": "SELECT customer_name, overdue_amount, company_code FROM dm.dm_customer_ar WHERE overdue_amount > 0 ORDER BY overdue_amount DESC",
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
1. 生成 3 个可能的假设（客户维度、时间维度）
2. 解释每个假设的合理性
3. 提出验证所需的 SQL 查询

## 数据库架构

dm.dm_ar_summary (AR 汇总表):
| stat_date | Date | 统计日期 |
| company_code | String | 公司代码 |
| company_name | String | 公司名称 |
| total_ar_amount | Decimal(18,2) | 应收总额 |
| received_amount | Decimal(18,2) | 已收金额 |
| overdue_amount | Decimal(18,2) | 逾期金额 |
| overdue_count | Int32 | 逾期单数 |
| total_count | Int32 | 总单数 |
| overdue_rate | Float32 | 逾期率 |

dm.dm_customer_ar (客户 AR 表):
| stat_date | Date | 统计日期 |
| customer_code | String | 客户代码 |
| customer_name | String | 客户名称 |
| company_code | String | 公司代码 |
| total_ar_amount | Decimal(18,2) | 应收总额 |
| overdue_amount | Decimal(18,2) | 逾期金额 |
| overdue_count | Int32 | 逾期单数 |
| total_count | Int32 | 应收单总数 |
| overdue_rate | Float32 | 逾期率 |

std.std_ar (AR 明细表):
| id | String | 单据ID |
| bill_no | String | 单据编号 |
| bill_date | DateTime | 单据日期 |
| bill_amount | Decimal(18,2) | 单据金额 |
| customer_name | String | 客户名称 |
| is_overdue | Bool | 是否逾期 |
| company_code | String | 公司代码 |

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
