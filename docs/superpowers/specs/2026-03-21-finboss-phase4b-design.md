# FinBoss Phase 4B - 客户 360 与数据治理

> 版本：v1.0
> 日期：2026-03-21
> 状态：待评审

---

## 一、目标概述

Phase 4B 基于金蝶 ERP 数据构建客户统一视图，为管理层、财务和 AI 归因提供一致的客户数据基础。

**Phase 4B 完成标准**：
- [ ] ERP 客户连接器抽象接口
- [ ] 客户标准化层（raw_customer）
- [ ] 模糊匹配引擎（基于 customer_name 相似度）
- [ ] 合并复核队列 + 飞书通知
- [ ] 客户 360 事实表（dm_customer360）
- [ ] 管理层看板 API（集中度/分布/趋势）
- [ ] 财务视图 API（账龄/付款历史/信用评分）
- [ ] AI 归因数据支持（客户维度扩展）

---

## 二、总体架构

```
ERP 连接器（ERPCustomerConnector 接口）
    │
    ├─ KingdeeCustomerConnector  ← Phase 4B 实现
    └─ (其他 ERP 接口预留，Phase 4A/4C 实现)
    │
    ▼
raw_customer 表（客户标准化）
    │
    ▼
客户匹配引擎
    │
    ├─ 相似度 > 0.95 → 自动合并
    ├─ 相似度 0.85~0.95 → 写入 pending_queue
    └─ 相似度 < 0.85 → 不处理
    │
    ├─→ pending_queue → 飞书卡片通知 → 运营确认/忽略
    │
    ▼
dm_customer360 事实表（每日物化）
    │
    ├─→ 管理层看板 API（集中度/分布/趋势）
    ├─→ 财务视图 API（账龄/付款/信用）
    └─→ AI 归因数据（客户维度）
```

---

## 三、模块一：ERP 客户连接器接口

### 3.1 抽象接口

```python
class RawCustomer(BaseModel):
    """标准化客户原始记录"""
    source_system: str           # ERP 来源，如 "kingdee"
    customer_id: str            # ERP 原始客户 ID
    customer_name: str          # 客户名称
    customer_short_name: str | None = None  # 客户简称
    tax_id: str | None = None              # 税号（如有）
    credit_code: str | None = None          # 统一社会信用代码（如有）
    address: str | None = None             # 注册地址
    contact: str | None = None            # 联系人
    phone: str | None = None               # 联系电话
    etl_time: datetime = Field(default_factory=datetime.now)


class RawARRecord(BaseModel):
    """标准化应收原始记录（用于客户账龄）"""
    source_system: str
    customer_id: str
    customer_name: str
    bill_no: str
    bill_date: date
    due_date: date
    bill_amount: Decimal
    received_amount: Decimal
    is_overdue: bool
    overdue_days: int
    company_code: str
    etl_time: datetime = Field(default_factory=datetime.now)


class ERPCustomerConnector(ABC):
    """ERP 客户数据连接器抽象接口

    所有 ERP 客户数据连接器必须实现此接口。
    Phase 4B 先实现 KingdeeCustomerConnector，
    未来接入其他 ERP 时新增实现类即可。
    """

    @property
    @abstractmethod
    def source_system(self) -> str:
        """ERP 来源标识，如 'kingdee', 'yonyou', 'sap'"""

    @abstractmethod
    def fetch_customers(self) -> list[RawCustomer]:
        """从 ERP 获取客户主数据"""

    @abstractmethod
    def fetch_ar_records(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawARRecord]:
        """从 ERP 获取应收明细（用于客户账龄分析）"""
```

### 3.2 金蝶实现

```python
class KingdeeCustomerConnector(ERPCustomerConnector):
    """金蝶客户连接器"""

    def __init__(self, db_config: KingdeeDBConfig | None = None):
        self._config = db_config or get_kingdee_config()

    @property
    def source_system(self) -> str:
        return "kingdee"

    def fetch_customers(self) -> list[RawCustomer]:
        """从金蝶客户主数据表获取客户信息

        注意：Phase 4B 仅使用 customer_id 和 customer_name。
        其他字段（tax_id, credit_code 等）在未来 ERP 接入时按需实现。
        """
        sql = """
        SELECT
            fitem3001 AS customer_id,
            fitem3002 AS customer_name,
            fitem3003 AS customer_short_name,
            fitem3004 AS address,
            fitem3005 AS contact,
            fitem3006 AS phone
        FROM t_item_3001  -- 客户主数据表（待确认实际表名）
        WHERE fitem3001 IS NOT NULL
        """
        rows = self._execute(sql)
        return [
            RawCustomer(
                source_system=self.source_system,
                customer_id=str(row["customer_id"]),
                customer_name=row["customer_name"] or "",
                customer_short_name=row.get("customer_short_name"),
                address=row.get("address"),
                contact=row.get("contact"),
                phone=row.get("phone"),
            )
            for row in rows
        ]

    def fetch_ar_records(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawARRecord]:
        """从金蝶应收单表获取应收明细"""
        # 使用已有的 KingdeeARIngester 的查询逻辑
        pass
```

---

## 四、模块二：客户标准化层

### 4.1 raw_customer 表

```sql
CREATE TABLE raw.raw_customer (
    id          String,
    source_system String,
    customer_id   String,
    customer_name String,
    short_name  String,
    tax_id       String,
    credit_code  String,
    address      String,
    contact      String,
    phone        String,
    etl_time     DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(etl_time);
```

**标准化规则**：
- `customer_name`：去除空格、括号内容、全角转半角
- `short_name`：从名称提取，如「深圳市腾讯计算机系统有限公司」→「腾讯」
- `id`：SHA256(source_system + customer_id)

### 4.2 CustomerStandardizer

```python
class CustomerStandardizer:
    """客户数据标准化"""

    def standardize(self, customer: RawCustomer) -> RawCustomer:
        """标准化客户数据"""
        import re
        import unidecode

        name = customer.customer_name

        # 去除空格
        name = re.sub(r"\s+", "", name)

        # 去除括号及其内容：「腾讯计算机（深圳）」→「腾讯计算机」
        name = re.sub(r"[（(].*?[）)]", "", name)

        # 全角转半角
        name = unidecode.unidecode(name)

        # 去除常见后缀
        for suffix in ["有限公司", "股份有限公司", "Ltd", "Co.", "Inc."]:
            name = name.replace(suffix, "")

        short_name = self._extract_short_name(name)

        return customer.model_copy(
            update={
                "customer_name": name,
                "short_name": short_name,
            }
        )

    def _extract_short_name(self, name: str) -> str:
        """提取客户简称"""
        # 取前4个字符作为简称
        return name[:4] if len(name) >= 4 else name
```

---

## 五、模块三：客户匹配引擎

### 5.1 匹配策略

**两层匹配**：
1. **精确匹配**：tax_id / credit_code 完全相同 → 直接合并
2. **模糊匹配**：基于名称相似度

```python
class CustomerMatcher:
    """客户匹配引擎"""

    SIMILARITY_HIGH = 0.95   # 自动合并阈值
    SIMILARITY_MED = 0.85    # 人工复核阈值

    def __init__(self):
        self._exact_cache: dict[str, list[str]] = {}  # tax_id → [customer_ids]

    def match(self, customers: list[RawCustomer]) -> list[MatchResult]:
        """对客户列表进行匹配，返回匹配结果"""
        results: list[MatchResult] = []
        seen: set[str] = set()

        for i, c1 in enumerate(customers):
            if c1.customer_id in seen:
                continue

            group = [c1]
            seen.add(c1.customer_id)

            for c2 in customers[i + 1:]:
                if c2.customer_id in seen:
                    continue

                similarity = self._calc_similarity(c1, c2)
                if similarity >= self.SIMILARITY_HIGH:
                    group.append(c2)
                    seen.add(c2.customer_id)
                elif similarity >= self.SIMILARITY_MED:
                    results.append(
                        MatchResult(
                            action="pending",
                            customers=[c1, c2],
                            similarity=similarity,
                            reason=f"名称相似度 {similarity:.2f}",
                        )
                    )

            if len(group) > 1:
                results.append(
                    MatchResult(
                        action="auto_merge",
                        customers=group,
                        similarity=1.0,
                        reason="名称完全相同",
                    )
                )

        return results

    def _calc_similarity(self, c1: RawCustomer, c2: RawCustomer) -> float:
        """计算两个客户的相似度"""
        # 精确匹配（优先）
        if c1.tax_id and c1.tax_id == c2.tax_id:
            return 1.0
        if c1.credit_code and c1.credit_code == c2.credit_code:
            return 1.0

        # 模糊匹配
        name_sim = self._name_similarity(c1.customer_name, c2.customer_name)

        # 简称辅助验证（简称相同权重 0.3）
        short_bonus = 0.0
        if c1.customer_short_name and c2.customer_short_name:
            if self._name_similarity(c1.customer_short_name, c2.customer_short_name) > 0.9:
                short_bonus = 0.3

        return min(name_sim + short_bonus, 1.0)

    def _name_similarity(self, name1: str, name2: str) -> float:
        """基于字符串相似度计算名称相似度"""
        import difflib
        return difflib.SequenceMatcher(None, name1, name2).ratio()
```

### 5.2 MatchResult 模型

```python
class MatchAction(str, Enum):
    AUTO_MERGE = "auto_merge"     # 自动合并
    PENDING = "pending"            # 待复核
    IGNORE = "ignore"              # 不处理


class MatchResult(BaseModel):
    """匹配结果"""
    action: MatchAction
    customers: list[RawCustomer]
    similarity: float
    reason: str
    created_at: datetime = Field(default_factory=datetime.now)


class CustomerMergeQueue(BaseModel):
    """合并复核队列"""
    id: str
    match_result: MatchResult
    status: Literal["pending", "confirmed", "rejected", "auto_merged"] = "pending"
    operator: str | None = None        # 飞书用户
    operated_at: datetime | None = None
    undo_record_id: str | None = None   # 撤销记录 ID
```

---

## 六、模块四：复核队列与飞书通知

### 6.1 每日批次流程

```
每日凌晨 02:00（每日批次结束后）
    │
    ├─→ CustomerMatcher.match() → 新的 match_results
    │
    ├─  auto_merge → 直接写入 dm_customer360
    │
    └─  pending →
            ├─→ 写入 customer_merge_queue 表
            └─→ 飞书卡片通知运营
                    │
                    ├─ [合并] 按钮 → 执行合并 → 更新 dm_customer360
                    │
                    └─ [忽略] 按钮 → 标记 rejected → 不再出现
```

### 6.2 飞书复核卡片

```python
def build_merge_card(result: MatchResult) -> dict:
    """构建合并复核卡片"""
    customers = result.customers
    return {
        "header": {
            "title": {"tag": "plain_text", "content": "🔔 客户合并待确认"},
            "template": "orange",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": f"**发现 {len(customers)} 个疑似同一客户：**\n\n"
                + "\n".join(f"- `{c.customer_id}` {c.customer_name}" for c in customers)
                + f"\n\n**相似度**：{result.similarity:.0%}\n**原因**：{result.reason}",
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✅ 合并"},
                        "type": "primary",
                        "value": f'{{"action": "merge", "queue_id": "{result.id}"}}',
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "❌ 忽略"},
                        "type": "danger",
                        "value": f'{{"action": "reject", "queue_id": "{result.id}"}}',
                    },
                ],
            },
        ],
    }
```

### 6.3 可逆合并

合并结果写入 `dm_customer360`，同时记录 `merge_history` 表：

```python
class MergeHistory(BaseModel):
    """合并历史（用于可逆）"""
    id: str
    unified_customer_code: str           # 合并后的统一编码
    source_system: str
    original_customer_id: str             # 合并前的原始 ID
    operated_at: datetime
    operator: str
    undo_record_id: str | None = None    # 如果被撤销，指向撤销记录
```

撤销操作：
1. 根据 `undo_record_id` 找到原记录
2. 从 `unified_customer_code` 中移除该 `original_customer_id`
3. 如果合并组只剩一个客户 → 恢复为独立客户
4. 记录新的撤销记录

---

## 七、模块五：客户 360 事实表

### 7.1 dm_customer360 表

```sql
CREATE TABLE dm.dm_customer360 (
    unified_customer_code  String,
    raw_customer_ids       Array(String),    -- 原始客户 ID 列表（合并后）
    source_systems         Array(String),   -- 来源系统
    customer_name          String,           -- 规范化名称
    customer_short_name    String,           -- 简称
    ar_total               Decimal(18,2),   -- 应收总额
    ar_overdue             Decimal(18,2),   -- 逾期金额
    overdue_rate           Float32,
    payment_score          Float32,          -- 付款信用分（0-100）
    last_payment_date      Date,
    last_ar_date           Date,            -- 最近一笔应收日期
    first_coop_date        Date,            -- 首次合作日期
    risk_level             String,           -- 高/中/低
    merge_status           String,           -- confirmed/pending/auto
    stat_date              Date,
    updated_at             DateTime,
    PRIMARY KEY (unified_customer_code, stat_date)
) ENGINE = SummingMergeTree()
ORDER BY (unified_customer_code, stat_date);
```

### 7.2 付款信用分算法

```python
def calc_payment_score(ar_records: list[RawARRecord]) -> float:
    """
    计算付款信用分（0-100）

    评分规则：
    - 逾期率扣分：每 1% 逾期率扣 2 分
    - 付款及时性加分：90天内付款 +5 分
    - 账龄结构扣分：超90天账龄占比 > 30% 扣 10 分
    - 合作时长加分：首次合作 > 2年 +5 分
    """
    if not ar_records:
        return 50.0  # 无数据返回中性分

    score = 100.0

    # 逾期率扣分
    overdue_count = sum(1 for r in ar_records if r.is_overdue)
    overdue_rate = overdue_count / len(ar_records)
    score -= overdue_rate * 200  # 每 1% 扣 2 分

    # 超长账龄扣分
    long_aging = sum(1 for r in ar_records if r.overdue_days > 90)
    if long_aging / len(ar_records) > 0.3:
        score -= 10

    # 近期付款加分
    recent_paid = sum(
        1 for r in ar_records
        if not r.is_overdue
        and (date.today() - r.bill_date).days < 90
    )
    if recent_paid / len(ar_records) > 0.7:
        score += 5

    return max(0.0, min(100.0, score))
```

### 7.3 风险等级

```python
def calc_risk_level(score: float, overdue_rate: float) -> str:
    """基于信用分和逾期率计算风险等级"""
    if overdue_rate > 0.3 or score < 40:
        return "高"
    elif overdue_rate > 0.1 or score < 70:
        return "中"
    return "低"
```

---

## 八、模块六：API 端点

### 8.1 管理层视图 API

**GET /api/v1/customer360/summary**

返回管理层视角的客户汇总数据：

```json
{
  "total_customers": 1234,
  "merged_customers": 45,
  "pending_merges": 3,
  "ar_total": 56789000.00,
  "ar_overdue_total": 2345678.00,
  "overall_overdue_rate": 4.13,
  "risk_distribution": {
    "高": 12,
    "中": 45,
    "低": 1177
  },
  "top10_ar_customers": [
    {"name": "客户A", "ar_total": 1234000.00, "overdue_rate": 0.05}
  ],
  "concentration_top10_ratio": 0.35
}
```

**GET /api/v1/customer360/distribution**

返回客户分布数据（用于图表）：

```json
{
  "by_company": [{"company": "C001", "count": 123, "ar_total": 1234000.00}],
  "by_risk_level": [{"risk": "高", "count": 12, "ar_total": 234000.00}],
  "by_overdue_bucket": [{"bucket": "0-30天", "count": 100, "amount": 500000.00}]
}
```

**GET /api/v1/customer360/trend**

返回客户/应收趋势（近12个月）：

```json
{
  "dates": ["2025-03", "2025-04", ...],
  "customer_counts": [1000, 1020, ...],
  "ar_totals": [50000000, 52000000, ...],
  "overdue_rates": [0.05, 0.06, ...]
}
```

### 8.2 财务视图 API

**GET /api/v1/customer360/{customer_code}/detail**

返回单个客户的财务详情：

```json
{
  "unified_customer_code": "C360_abc123",
  "customer_name": "腾讯",
  "raw_customers": [
    {"id": "K001", "name": "深圳市腾讯计算机系统有限公司", "source": "kingdee"}
  ],
  "ar_total": 1234000.00,
  "ar_overdue": 123456.00,
  "overdue_rate": 0.10,
  "payment_score": 75.0,
  "risk_level": "中",
  "last_payment_date": "2025-02-28",
  "first_coop_date": "2022-01-01",
  "aging_distribution": {
    "0-30天": 500000.00,
    "31-60天": 300000.00,
    "61-90天": 234000.00,
    "90天以上": 200000.00
  },
  "recent_bills": [
    {"bill_no": "AR202503001", "amount": 100000.00, "status": "逾期", "overdue_days": 15}
  ]
}
```

### 8.3 合并复核 API

**GET /api/v1/customer360/merge-queue**

返回待复核合并队列：

```json
{
  "items": [
    {
      "id": "mq_001",
      "similarity": 0.91,
      "reason": "名称相似度 0.91",
      "customers": [
        {"customer_id": "K001", "name": "腾讯科技", "source": "kingdee"},
        {"customer_id": "K002", "name": "腾讯科技（深圳）有限公司", "source": "kingdee"}
      ],
      "created_at": "2025-03-21T02:00:00"
    }
  ],
  "total": 3
}
```

**POST /api/v1/customer360/merge-queue/{id}/confirm**

确认合并：

```json
{"action": "confirm"}
```

**POST /api/v1/customer360/merge-queue/{id}/reject**

忽略：

```json
{"action": "reject"}
```

**POST /api/v1/customer360/{customer_code}/undo**

撤销合并：

```json
{"original_customer_id": "K002", "reason": "误合并"}
```

### 8.4 AI 归因数据 API

**GET /api/v1/customer360/attribution**

返回客户维度归因所需数据（供 AttributionService 使用）：

```json
{
  "dimension": "customer",
  "data": [
    {
      "customer_code": "C360_abc",
      "customer_name": "客户A",
      "ar_overdue_curr": 100000.00,
      "ar_overdue_prev": 50000.00,
      "overdue_delta": 50000.00,
      "overdue_rate_curr": 0.15,
      "overdue_rate_prev": 0.08,
      "risk_level": "高"
    }
  ]
}
```

---

## 九、每日批次调度

### 9.1 调度流程

```
每日 02:00
  │
  ├─ 步骤1: 从各 ERP 拉取客户数据
  │       ERPCustomerConnectorRegistry.fetch_all()
  │
  ├─ 步骤2: 写入 raw_customer 表
  │       CustomerStandardizer.standardize()
  │
  ├─ 步骤3: 执行匹配引擎
  │       CustomerMatcher.match()
  │         ├─ auto_merge → dm_customer360
  │         └─ pending → customer_merge_queue
  │
  ├─ 步骤4: 飞书通知（有待复核时）
  │       FeishuClient.send_merge_notification()
  │
  └─ 步骤5: 刷新 dm_customer360 事实表
            Customer360Generator.generate()
```

### 9.2 ERPCustomerConnectorRegistry

```python
class ERPCustomerConnectorRegistry:
    """ERP 连接器注册表（支持多 ERP）"""

    _connectors: dict[str, type[ERPCustomerConnector]] = {}

    @classmethod
    def register(cls, source_system: str, connector_cls: type[ERPCustomerConnector]):
        cls._connectors[source_system] = connector_cls

    @classmethod
    def get(cls, source_system: str) -> ERPCustomerConnector:
        if source_system not in cls._connectors:
            raise ValueError(f"未注册的 ERP: {source_system}")
        return cls._connectors[source_system]()

    @classmethod
    def fetch_all_customers(cls) -> list[RawCustomer]:
        """从所有已注册的 ERP 获取客户数据"""
        results = []
        for source, cls_ in cls._connectors.items():
            try:
                connector = cls_()
                results.extend(connector.fetch_customers())
            except Exception as e:
                logger.warning(f"ERP {source} 拉取失败: {e}")
        return results

    @classmethod
    def fetch_all_ar_records(cls, **kwargs) -> list[RawARRecord]:
        """从所有已注册的 ERP 获取应收数据"""
        results = []
        for source, cls_ in cls._connectors.items():
            try:
                connector = cls_()
                results.extend(connector.fetch_ar_records(**kwargs))
            except Exception as e:
                logger.warning(f"ERP {source} 应收拉取失败: {e}")
        return results
```

注册时调用：

```python
# 初始化时注册
ERPCustomerConnectorRegistry.register("kingdee", KingdeeCustomerConnector)
# 未来扩展
# ERPCustomerConnectorRegistry.register("yonyou", YonyouCustomerConnector)
```

---

## 十、数据模型

### 10.1 schemas/customer360.py

```python
class Customer360Record(BaseModel):
    """客户 360 事实表记录"""
    unified_customer_code: str
    raw_customer_ids: list[str]
    source_systems: list[str]
    customer_name: str
    customer_short_name: str | None = None
    ar_total: Decimal
    ar_overdue: Decimal
    overdue_rate: float
    payment_score: float
    risk_level: Literal["高", "中", "低"]
    merge_status: Literal["confirmed", "pending", "auto"]
    stat_date: date
    updated_at: datetime


class Customer360Summary(BaseModel):
    """管理层汇总"""
    total_customers: int
    merged_customers: int
    pending_merges: int
    ar_total: Decimal
    ar_overdue_total: Decimal
    overall_overdue_rate: float
    risk_distribution: dict[str, int]
    concentration_top10_ratio: float


class MergeQueueItem(BaseModel):
    """合并复核队列项"""
    id: str
    similarity: float
    reason: str
    customers: list[RawCustomer]
    created_at: datetime
    status: Literal["pending", "confirmed", "rejected"]
```

---

## 十一、已知限制

1. **无税号/信用代码**：Phase 4B 仅基于 `customer_name` 做模糊匹配，无法做精确匹配
2. **仅金蝶 ERP**：其他 ERP 连接器预留接口，待实际接入时实现
3. **每日批次**：不支持准实时更新（设计为 T+1）
4. **相似度阈值固定**：0.85/0.95 阈值在初期可能需要调整

---

## 十二、依赖关系

```
Phase 4B 依赖

erp_connector (抽象接口)
  └─ KingdeeCustomerConnector (Phase 4B)
        └─ KingdeeDBConfig (Phase 1)

customer_standardizer
  └─ unidecode (pip install)

customer_matcher
  └─ difflib (Python 内置)

customer360_service
  ├─ ClickHouseDataService (Phase 1)
  └─ ERPCustomerConnectorRegistry

feishu_merge_notification
  └─ FeishuClient (Phase 3)

attribution扩展 (客户维度)
  └─ AttributionService (Phase 3)
```

---

*Phase 4B 版本：v1.0*
