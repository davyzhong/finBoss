# Phase 4B 客户360 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于金蝶 ERP 构建客户统一视图，包含模糊匹配引擎、合并复核队列、dm_customer360 事实表及管理层/财务/AI 归因 API。

**Architecture:** ERP 客户连接器（抽象接口）→ 标准化层 → 模糊匹配引擎 → 合并队列 + 飞书通知 → dm_customer360 事实表 → API 层。每日 02:00 APScheduler 批量刷新。

**Tech Stack:** Python 3.11, FastAPI, ClickHouse, APScheduler, difflib, unidecode, lark-oapi (飞书)

---

## 文件结构总览

```
新增文件:
  schemas/customer360.py               # 数据模型（RawCustomer, MatchResult, Customer360Record 等）
  connectors/customer/__init__.py      # ERP 连接器包
  connectors/customer/base.py          # ERPCustomerConnector ABC + RawCustomer/RawARRecord 模型
  connectors/customer/kingdee.py       # KingdeeCustomerConnector 实现
  services/customer360_service.py      # 核心业务服务（标准化/匹配/360生成）
  services/scheduler_service.py         # APScheduler 每日调度
  api/routes/customer360.py             # 客户360 API 路由
  api/schemas/customer360.py            # API 请求/响应 Pydantic 模型
  scripts/customer360_ddl.sql           # ClickHouse DDL（raw_customer, dm_customer360, merge_queue）
  scripts/init_customer360.py            # 初始化脚本
  tests/unit/test_customer360_service.py
  tests/unit/test_customer_matcher.py
  tests/integration/test_customer360_api.py

修改文件:
  pyproject.toml                       # +apscheduler, +unidecode
  api/dependencies.py                   # +get_customer360_service
  api/main.py                          # 注册 customer360 路由
  services/feishu/feishu_client.py      # +send_merge_notification
  api/config.py                        # +FeishuOpsChannelConfig
```

---

## Task 1: 添加依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 添加 apscheduler 和 unidecode 依赖**

在 `[dependencies]` 数组末尾添加：

```toml
    # Scheduling
    "apscheduler>=3.10.4",
    # Text normalization
    "unidecode>=1.3.8",
```

Run: `uv sync`
Expected: 两个新包被安装，无冲突

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add apscheduler and unidecode for Phase 4B"
```

---

## Task 2: 数据模型 schemas/customer360.py

**Files:**
- Create: `schemas/customer360.py`

- [ ] **Step 1: 写测试（models 已有 spec 定义，直接写单元测试验证模型行为）**

```python
# tests/unit/test_customer360_models.py
"""测试客户360数据模型"""
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from schemas.customer360 import (
    RawCustomer,
    RawARRecord,
    MatchAction,
    MatchResult,
    CustomerMergeQueue,
    Customer360Record,
    MergeHistory,
)


class TestRawCustomer:
    def test_required_fields_only(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯科技",
        )
        assert c.source_system == "kingdee"
        assert c.customer_id == "K001"
        assert c.customer_name == "腾讯科技"
        assert c.customer_short_name is None
        assert c.etl_time is not None

    def test_all_fields(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯科技",
            customer_short_name="腾讯",
            tax_id="91440300MA5D12345X",
            credit_code="91440300MA5D12345X",
            address="深圳南山区",
            contact="张三",
            phone="13800138000",
        )
        assert c.tax_id == "91440300MA5D12345X"
        assert c.credit_code == "91440300MA5D12345X"

    def test_etl_time_auto_now(self):
        c = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        assert c.etl_time is not None


class TestMatchResult:
    def test_auto_merge_result(self):
        customer = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        result = MatchResult(
            action=MatchAction.AUTO_MERGE,
            customers=[customer],
            unified_customer_code="C360_abc123",
            similarity=1.0,
            reason="名称完全相同",
        )
        assert result.action == MatchAction.AUTO_MERGE
        assert result.unified_customer_code == "C360_abc123"

    def test_pending_result(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯科技")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯科技（深圳）")
        result = MatchResult(
            action=MatchAction.PENDING,
            customers=[c1, c2],
            similarity=0.91,
            reason="名称相似度 0.91",
        )
        assert result.action == MatchAction.PENDING
        assert result.unified_customer_code is None


class TestCustomerMergeQueue:
    def test_default_status_is_pending(self):
        customer = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        match = MatchResult(
            action=MatchAction.PENDING,
            customers=[customer],
            similarity=0.9,
            reason="test",
        )
        q = CustomerMergeQueue(id="mq_001", match_result=match)
        assert q.status == "pending"
        assert q.operator is None
        assert q.operated_at is None

    def test_all_status_values(self):
        for status in ["pending", "confirmed", "rejected", "auto_merged"]:
            customer = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
            match = MatchResult(
                action=MatchAction.AUTO_MERGE if status == "auto_merged" else MatchAction.PENDING,
                customers=[customer],
                similarity=1.0,
                reason="test",
            )
            q = CustomerMergeQueue(id="mq_001", match_result=match, status=status)
            assert q.status == status
```

- [ ] **Step 2: 运行测试确认失败（缺少模块）**

Run: `uv run pytest tests/unit/test_customer360_models.py -v`
Expected: FAIL — `ImportError: cannot import 'schemas.customer360'`

- [ ] **Step 3: 创建 schemas/customer360.py**

```python
# schemas/customer360.py
"""客户360数据模型"""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class RawCustomer(BaseModel):
    """标准化客户原始记录"""
    source_system: str
    customer_id: str
    customer_name: str
    customer_short_name: str | None = None
    tax_id: str | None = None
    credit_code: str | None = None
    address: str | None = None
    contact: str | None = None
    phone: str | None = None
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


class MatchAction(str, Enum):
    AUTO_MERGE = "auto_merge"
    PENDING = "pending"
    IGNORE = "ignore"


class MatchResult(BaseModel):
    """匹配结果"""
    action: MatchAction
    customers: list[RawCustomer]
    unified_customer_code: str | None = None
    similarity: float
    reason: str
    created_at: datetime = Field(default_factory=datetime.now)


class CustomerMergeQueue(BaseModel):
    """合并复核队列"""
    id: str
    match_result: MatchResult
    status: Literal["pending", "confirmed", "rejected", "auto_merged"] = "pending"
    operator: str | None = None
    operated_at: datetime | None = None
    undo_record_id: str | None = None


class Customer360Record(BaseModel):
    """客户360事实表记录"""
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
    merge_status: Literal["pending", "confirmed", "auto_merged"]
    last_payment_date: date | None = None  # 最近付款日期，从已核销应收记录计算
    first_coop_date: date | None = None   # 首次合作日期，从最早期应收记录计算
    company_code: str | None = None       # 主要公司编码（用于按公司维度统计）
    stat_date: date
    updated_at: datetime

    class Config:
        from_attributes = True


class Customer360Summary(BaseModel):
    """管理层汇总视图"""
    total_customers: int
    merged_customers: int
    pending_merges: int
    ar_total: Decimal
    ar_overdue_total: Decimal
    overall_overdue_rate: float
    risk_distribution: dict[str, int]
    concentration_top10_ratio: float
    top10_ar_customers: list[dict] = Field(default_factory=list)  # [{name, ar_total, overdue_rate}]


class MergeHistory(BaseModel):
    """合并历史（用于可逆操作）"""
    id: str
    unified_customer_code: str
    source_system: str
    original_customer_id: str
    operated_at: datetime
    operator: str
    undo_record_id: str | None = None


class CustomerDistribution(BaseModel):
    """客户分布数据"""
    by_company: list[dict]
    by_risk_level: list[dict]
    by_overdue_bucket: list[dict]


class CustomerTrend(BaseModel):
    """客户/应收趋势"""
    dates: list[str]
    customer_counts: list[int]
    ar_totals: list[float]
    overdue_rates: list[float]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_customer360_models.py -v`
Expected: PASS（5 tests）

- [ ] **Step 5: Commit**

```bash
git add schemas/customer360.py tests/unit/test_customer360_models.py
git commit -m "feat: add customer360 data models (schemas)"
```

---

## Task 3: ERP 客户连接器（接口 + 金蝶实现）

**Files:**
- Create: `connectors/customer/__init__.py`
- Create: `connectors/customer/base.py`
- Create: `connectors/customer/kingdee.py`
- Test: `tests/unit/test_customer_connector.py`

- [ ] **Step 1: 写连接器基类测试**

```python
# tests/unit/test_customer_connector.py
"""测试 ERP 客户连接器"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from connectors.customer.base import ERPCustomerConnector, RawCustomer, RawARRecord
from connectors.customer.kingdee import KingdeeCustomerConnector


class TestERPCustomerConnector:
    def test_is_abc(self):
        """验证是抽象基类，不能直接实例化"""
        with pytest.raises(TypeError):
            ERPCustomerConnector()


class TestKingdeeCustomerConnector:
    def test_source_system_property(self):
        conn = KingdeeCustomerConnector()
        assert conn.source_system == "kingdee"

    def test_fetch_customers_returns_list(self):
        """mock KingdeeDBConfig，避免真实连接"""
        with patch("connectors.customer.kingdee.get_kingdee_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.host = "localhost"
            mock_cfg.port = 1433
            mock_cfg.user = "sa"
            mock_cfg.password = "password"
            mock_cfg.name = "AIS20220323153128"
            mock_cfg.jdbc_url = "jdbc:jtds:sqlserver://localhost:1433;AIS20220323153128"
            mock_config.return_value = mock_cfg

            with patch.object(KingdeeCustomerConnector, "_execute", return_value=[]):
                conn = KingdeeCustomerConnector()
                result = conn.fetch_customers()
                assert isinstance(result, list)

    def test_fetch_customers_maps_fields(self):
        with patch("connectors.customer.kingdee.get_kingdee_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.jdbc_url = "jdbc:jtds:sqlserver://localhost:1433;DB"
            mock_config.return_value = mock_cfg

            mock_rows = [
                {
                    "customer_id": "K001",
                    "customer_name": "腾讯科技",
                    "customer_short_name": "腾讯",
                    "address": "深圳",
                    "contact": "张三",
                    "phone": "13800138000",
                }
            ]
            with patch.object(KingdeeCustomerConnector, "_execute", return_value=mock_rows):
                conn = KingdeeCustomerConnector()
                customers = conn.fetch_customers()
                assert len(customers) == 1
                assert customers[0].customer_id == "K001"
                assert customers[0].customer_name == "腾讯科技"
                assert customers[0].customer_short_name == "腾讯"

    def test_fetch_ar_records_uses_ingester(self):
        """验证复用 KingdeeARIngester"""
        with patch("connectors.customer.kingdee.get_kingdee_config") as mock_config:
            mock_cfg = MagicMock()
            mock_config.return_value = mock_cfg

            mock_ingester = MagicMock()
            mock_ingester.fetch_ar_records.return_value = []
            with patch(
                "connectors.kingdee.client.KingdeeARIngester",
                return_value=mock_ingester,
            ):
                conn = KingdeeCustomerConnector()
                conn.fetch_ar_records(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
                mock_ingester.fetch_ar_records.assert_called_once_with(
                    start_date=date(2025, 1, 1),
                    end_date=date(2025, 12, 31),
                )
```

- [ ] **Step 2: 运行测试确认失败（模块不存在）**

Run: `uv run pytest tests/unit/test_customer_connector.py -v`
Expected: FAIL — `ImportError: cannot import 'connectors.customer'`

- [ ] **Step 3: 创建 connectors/customer/__init__.py**

```python
# connectors/customer/__init__.py
"""ERP 客户连接器"""
from connectors.customer.base import (
    ERPCustomerConnector,
    ERPCustomerConnectorRegistry,
    RawCustomer,
    RawARRecord,
)
from connectors.customer.kingdee import KingdeeCustomerConnector

# 注册默认连接器
ERPCustomerConnectorRegistry.register("kingdee", KingdeeCustomerConnector)

__all__ = [
    "ERPCustomerConnector",
    "ERPCustomerConnectorRegistry",
    "RawCustomer",
    "RawARRecord",
    "KingdeeCustomerConnector",
]
```

- [ ] **Step 4: 创建 connectors/customer/base.py**

```python
# connectors/customer/base.py
"""ERP 客户连接器抽象接口"""
from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from schemas.customer360 import RawCustomer, RawARRecord


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


class ERPCustomerConnectorRegistry:
    """ERP 连接器注册表（支持多 ERP）"""

    _connectors: dict[str, type[ERPCustomerConnector]] = {}

    @classmethod
    def register(cls, source_system: str, connector_cls: type[ERPCustomerConnector]) -> None:
        if not issubclass(connector_cls, ERPCustomerConnector):
            raise TypeError(f"{connector_cls} must inherit from ERPCustomerConnector")
        cls._connectors[source_system] = connector_cls

    @classmethod
    def get(cls, source_system: str) -> ERPCustomerConnector:
        if source_system not in cls._connectors:
            raise ValueError(f"未注册的 ERP: {source_system}")
        return cls._connectors[source_system]()

    @classmethod
    def fetch_all_customers(cls) -> list[RawCustomer]:
        """从所有已注册的 ERP 获取客户数据"""
        results: list[RawCustomer] = []
        for source, connector_cls in cls._connectors.items():
            try:
                connector = connector_cls()
                results.extend(connector.fetch_customers())
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"ERP {source} 拉取失败: {e}")
        return results

    @classmethod
    def fetch_all_ar_records(
        cls,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawARRecord]:
        """从所有已注册的 ERP 获取应收数据"""
        results: list[RawARRecord] = []
        for source, connector_cls in cls._connectors.items():
            try:
                connector = connector_cls()
                results.extend(connector.fetch_ar_records(start_date=start_date, end_date=end_date))
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"ERP {source} 应收拉取失败: {e}")
        return results
```

- [ ] **Step 5: 创建 connectors/customer/kingdee.py**

```python
# connectors/customer/kingdee.py
"""金蝶客户连接器"""
import logging
from datetime import date
from typing import Any

import pymssql

from api.config import KingdeeDBConfig, get_settings
from connectors.customer.base import ERPCustomerConnector
from schemas.customer360 import RawCustomer, RawARRecord

logger = logging.getLogger(__name__)


class KingdeeCustomerConnector(ERPCustomerConnector):
    """金蝶客户连接器

    复用已有的 KingdeeARIngester（connectors/kingdee/client.py）进行应收数据查询。
    客户主数据从金蝶客户主数据表获取（表名待实施团队确认金蝶实际表名）。
    """

    def __init__(self, db_config: KingdeeDBConfig | None = None):
        self._config = db_config or get_settings().kingdee

    @property
    def source_system(self) -> str:
        return "kingdee"

    def _execute(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """执行 SQL 查询，返回字典列表"""
        conn = pymssql.connect(
            server=self._config.host,
            port=self._config.port,
            user=self._config.user,
            password=self._config.password,
            database=self._config.name,
        )
        try:
            with conn.cursor(as_dict=True) as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        finally:
            conn.close()

    def fetch_customers(self) -> list[RawCustomer]:
        """从金蝶客户主数据表获取客户信息

        表名说明：
        - **需实施团队确认**：金蝶 ERP 的客户主数据表名（常见如 t_bd_customer、t_pm_branch 等不同版本表名不同）。
        - Phase 4B 实现前，团队需在金蝶管理后台确认实际表名及字段映射。
        - 此处 SQL 为占位符，标注了需要替换的位置。
        """
        # TODO(实施): 替换为实际客户主数据表名
        customer_table = "t_bd_customer"  # ← 待确认
        sql = f"""
        SELECT
            fitem3001 AS customer_id,
            fitem3002 AS customer_name,
            fitem3003 AS customer_short_name,
            fitem3004 AS address,
            fitem3005 AS contact,
            fitem3006 AS phone
        FROM {customer_table}
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
        """从金蝶应收单表获取应收明细

        复用 connectors/kingdee/client.py 中的 KingdeeARIngester 查询方法。
        """
        from connectors.kingdee.client import KingdeeARIngester

        ingester = KingdeeARIngester(self._config)
        raw_records = ingester.fetch_ar_records(start_date=start_date, end_date=end_date)
        return [
            RawARRecord(
                source_system=self.source_system,
                customer_id=r.customer_id,
                customer_name=r.customer_name,
                bill_no=r.bill_no,
                bill_date=r.bill_date,
                due_date=r.due_date,
                bill_amount=r.bill_amount,
                received_amount=r.received_amount,
                is_overdue=r.is_overdue,
                overdue_days=r.overdue_days,
                company_code=r.company_code,
            )
            for r in raw_records
        ]
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_customer_connector.py -v`
Expected: PASS（5 tests）

- [ ] **Step 7: Commit**

```bash
git add connectors/customer/ tests/unit/test_customer_connector.py
git commit -m "feat: add ERP customer connector (abstract + Kingdee impl)"
```

---

## Task 4: 客户标准化层（CustomerStandardizer）

**Files:**
- Create: `services/customer_standardizer.py`
- Test: `tests/unit/test_customer_standardizer.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_customer_standardizer.py
"""测试客户数据标准化"""
import pytest

from schemas.customer360 import RawCustomer
from services.customer_standardizer import CustomerStandardizer


class TestCustomerStandardizer:
    def setup_method(self):
        self.std = CustomerStandardizer()

    def test_removes_spaces(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="深圳 腾讯 计算机",
        )
        result = self.std.standardize(c)
        assert " " not in result.customer_name

    def test_removes_parentheses(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯计算机（深圳）有限公司",
        )
        result = self.std.standardize(c)
        assert "（" not in result.customer_name
        assert "(" not in result.customer_name
        assert "深圳" not in result.customer_name

    def test_removes_common_suffixes(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯科技有限公司",
        )
        result = self.std.standardize(c)
        assert "有限公司" not in result.customer_name

    def test_fullwidth_to_halfwidth(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯计算机有限公司",
        )
        result = self.std.standardize(c)
        # 全角字符被转换
        assert result.customer_name is not None
        assert len(result.customer_name) > 0

    def test_short_name_first_4_chars(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="深圳市腾讯计算机系统有限公司",
        )
        result = self.std.standardize(c)
        assert result.customer_short_name == "深圳市腾讯"

    def test_short_name_short_name(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯",
        )
        result = self.std.standardize(c)
        assert result.customer_short_name == "腾讯"

    def test_preserves_original_fields(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯科技",
            address="深圳",
            contact="张三",
        )
        result = self.std.standardize(c)
        assert result.customer_id == "K001"
        assert result.source_system == "kingdee"
        assert result.address == "深圳"
        assert result.contact == "张三"

    def test_returns_new_instance(self):
        c = RawCustomer(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯科技",
        )
        result = self.std.standardize(c)
        assert result is not c
        assert c.customer_name == "腾讯科技"  # 原始不变
```

- [ ] **Step 2: 运行测试确认失败（模块不存在）**

Run: `uv run pytest tests/unit/test_customer_standardizer.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 创建 services/customer_standardizer.py**

```python
# services/customer_standardizer.py
"""客户数据标准化服务"""
import re
import unicodedata

from schemas.customer360 import RawCustomer


class CustomerStandardizer:
    """客户数据标准化

    标准化规则：
    - customer_name：去除空格、括号内容、全角转半角、去除常见后缀
    - customer_short_name：从标准化后的名称提取前4字符
    """

    COMMON_SUFFIXES = [
        "有限公司",
        "股份有限公司",
        "有限责任公司",
        "Ltd",
        "Ltd.",
        "Co.",
        "Co",
        "Inc.",
        "Inc",
    ]

    def standardize(self, customer: RawCustomer) -> RawCustomer:
        """标准化客户数据，返回新的 RawCustomer 实例（不修改原对象）"""
        name = customer.customer_name

        # 去除空格
        name = re.sub(r"\s+", "", name)

        # 去除括号及其内容：「腾讯计算机（深圳）」→「腾讯计算机」
        name = re.sub(r"[（(].*?[）)]", "", name)

        # 全角转半角
        name = self._fullwidth_to_halfwidth(name)

        # 去除常见后缀
        for suffix in self.COMMON_SUFFIXES:
            name = name.replace(suffix, "")

        short_name = self._extract_short_name(name)

        return customer.model_copy(
            update={
                "customer_name": name,
                "customer_short_name": short_name,
            }
        )

    def _fullwidth_to_halfwidth(self, text: str) -> str:
        """全角转半角"""
        result = []
        for char in text:
            inside = ord(0xFEE0) + ord(char)
            if 0xFF01 <= ord(char) <= 0xFF5E:
                result.append(chr(inside))
            else:
                result.append(char)
        return "".join(result)

    def _extract_short_name(self, name: str) -> str:
        """提取客户简称（标准化后的名称前4字符）"""
        return name[:4] if len(name) >= 4 else name
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_customer_standardizer.py -v`
Expected: PASS（7 tests）

- [ ] **Step 5: Commit**

```bash
git add services/customer_standardizer.py tests/unit/test_customer_standardizer.py
git commit -m "feat: add CustomerStandardizer service"
```

---

## Task 5: 客户匹配引擎（CustomerMatcher）

**Files:**
- Create: `services/customer_matcher.py`
- Test: `tests/unit/test_customer_matcher.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_customer_matcher.py
"""测试客户匹配引擎"""
import pytest

from schemas.customer360 import MatchAction, MatchResult, RawCustomer
from services.customer_matcher import CustomerMatcher


class TestCustomerMatcher:
    def setup_method(self):
        self.matcher = CustomerMatcher()

    def test_name_similarity_identical(self):
        sim = self.matcher._name_similarity("腾讯科技", "腾讯科技")
        assert sim == 1.0

    def test_name_similarity_similar(self):
        sim = self.matcher._name_similarity("腾讯科技（深圳）有限公司", "腾讯科技有限公司")
        assert sim > 0.8

    def test_name_similarity_different(self):
        sim = self.matcher._name_similarity("腾讯", "阿里巴巴")
        assert sim < 0.5

    def test_calc_similarity_exact_match(self):
        c1 = RawCustomer(
            source_system="kingdee", customer_id="K001",
            customer_name="腾讯", tax_id="123456789"
        )
        c2 = RawCustomer(
            source_system="kingdee", customer_id="K002",
            customer_name="腾讯", tax_id="123456789"
        )
        assert self.matcher._calc_similarity(c1, c2) == 1.0

    def test_calc_similarity_credit_code_match(self):
        c1 = RawCustomer(
            source_system="kingdee", customer_id="K001",
            customer_name="腾讯", credit_code="ABC123"
        )
        c2 = RawCustomer(
            source_system="kingdee", customer_id="K002",
            customer_name="腾讯", credit_code="ABC123"
        )
        assert self.matcher._calc_similarity(c1, c2) == 1.0

    def test_calc_similarity_no_match_fields(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯科技")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="阿里巴巴")
        sim = self.matcher._calc_similarity(c1, c2)
        assert 0.0 <= sim <= 1.0
        assert sim < 0.5

    def test_generate_unified_code_deterministic(self):
        c = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        code1 = self.matcher._generate_unified_code([c])
        code2 = self.matcher._generate_unified_code([c])
        assert code1 == code2
        assert code1.startswith("C360_")

    def test_generate_unified_code_different_customers_different_codes(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="阿里")
        code1 = self.matcher._generate_unified_code([c1])
        code2 = self.matcher._generate_unified_code([c2])
        assert code1 != code2

    def test_match_empty_list(self):
        results = self.matcher.match([])
        assert results == []

    def test_match_single_customer_no_group(self):
        c = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        results = self.matcher.match([c])
        # 单个客户无匹配，返回空
        assert results == []

    def test_match_identical_names_auto_merge(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯")
        results = self.matcher.match([c1, c2])
        assert len(results) == 1
        assert results[0].action == MatchAction.AUTO_MERGE
        assert len(results[0].customers) == 2
        assert results[0].unified_customer_code is not None

    def test_match_similar_names_pending(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯科技")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯科技（深圳）")
        results = self.matcher.match([c1, c2])
        pending = [r for r in results if r.action == MatchAction.PENDING]
        assert len(pending) == 1
        assert pending[0].similarity < 0.95
        assert pending[0].similarity >= 0.85

    def test_match_different_names_ignored(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="阿里巴巴")
        results = self.matcher.match([c1, c2])
        # 相似度低于阈值，无结果
        assert results == []

    def test_match_skips_seen_customers(self):
        """验证每个客户只被匹配一次（seen 集合正确工作）"""
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯")
        c3 = RawCustomer(source_system="kingdee", customer_id="K003", customer_name="腾讯")
        results = self.matcher.match([c1, c2, c3])
        # K001/K002 合并，K003 与 K001 已同组，不再匹配
        auto_merges = [r for r in results if r.action == MatchAction.AUTO_MERGE]
        assert len(auto_merges) == 1
        assert len(auto_merges[0].customers) == 2
```

- [ ] **Step 2: 运行测试确认失败（模块不存在）**

Run: `uv run pytest tests/unit/test_customer_matcher.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 创建 services/customer_matcher.py**

```python
# services/customer_matcher.py
"""客户匹配引擎"""
import difflib
import hashlib
import logging
from datetime import datetime

from schemas.customer360 import MatchAction, MatchResult, RawCustomer

logger = logging.getLogger(__name__)


class CustomerMatcher:
    """客户匹配引擎

    两层匹配策略：
    1. 精确匹配：tax_id / credit_code 完全相同 → 直接合并
    2. 模糊匹配：基于名称相似度（difflib.SequenceMatcher）
    """

    SIMILARITY_HIGH = 0.95  # 自动合并阈值
    SIMILARITY_MED = 0.85   # 人工复核阈值

    def match(self, customers: list[RawCustomer]) -> list[MatchResult]:
        """对客户列表进行匹配，返回匹配结果列表"""
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
                            action=MatchAction.PENDING,
                            customers=[c1, c2],
                            similarity=similarity,
                            reason=f"名称相似度 {similarity:.2f}",
                        )
                    )

            if len(group) > 1:
                unified_code = self._generate_unified_code(group)
                results.append(
                    MatchResult(
                        action=MatchAction.AUTO_MERGE,
                        customers=group,
                        unified_customer_code=unified_code,
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

        # 简称辅助验证（简称相同权重 +0.3）
        short_bonus = 0.0
        if c1.customer_short_name and c2.customer_short_name:
            if self._name_similarity(c1.customer_short_name, c2.customer_short_name) > 0.9:
                short_bonus = 0.3

        return min(name_sim + short_bonus, 1.0)

    def _generate_unified_code(self, customers: list[RawCustomer]) -> str:
        """为合并组生成统一客户编码（SHA256，固定12位十六进制前缀）"""
        first = customers[0]
        raw = f"{first.source_system}:{first.customer_id}"
        return f"C360_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"

    def _name_similarity(self, name1: str, name2: str) -> float:
        """基于字符串相似度计算名称相似度"""
        return difflib.SequenceMatcher(None, name1, name2).ratio()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_customer_matcher.py -v`
Expected: PASS（10 tests）

- [ ] **Step 5: Commit**

```bash
git add services/customer_matcher.py tests/unit/test_customer_matcher.py
git commit -m "feat: add CustomerMatcher fuzzy matching engine"
```

---

## Task 6: 客户360 核心服务（Customer360Service）

**Files:**
- Create: `services/customer360_service.py`
- Test: `tests/unit/test_customer360_service.py`

- [ ] **Step 1: 写测试（payment_score + risk_level 算法）**

```python
# tests/unit/test_customer360_service.py
"""测试客户360核心服务"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from schemas.customer360 import (
    Customer360Record,
    MatchAction,
    MatchResult,
    RawARRecord,
    RawCustomer,
)
from services.customer360_service import (
    Customer360Generator,
    Customer360Service,
    PaymentScoreCalculator,
    RiskLevelCalculator,
)


class TestPaymentScoreCalculator:
    def setup_method(self):
        self.calc = PaymentScoreCalculator()

    def test_no_records_returns_50(self):
        score = self.calc.calculate([])
        assert score == 50.0

    def test_full_payment_no_overdue(self):
        records = [
            self._make_ar(is_overdue=False, bill_date=date.today(), overdue_days=0)
            for _ in range(10)
        ]
        score = self.calc.calculate(records)
        assert score == 100.0

    def test_all_overdue_high_rate(self):
        records = [self._make_ar(is_overdue=True, overdue_days=10) for _ in range(10)]
        score = self.calc.calculate(records)
        assert score == 0.0

    def test_score_bounded_0_100(self):
        records = [self._make_ar(is_overdue=True, overdue_days=200) for _ in range(100)]
        score = self.calc.calculate(records)
        assert 0.0 <= score <= 100.0

    def _make_ar(self, is_overdue: bool, overdue_days: int = 0, bill_date: date | None = None) -> RawARRecord:
        if bill_date is None:
            bill_date = date(2025, 1, 1)
        return RawARRecord(
            source_system="kingdee",
            customer_id="K001",
            customer_name="腾讯",
            bill_no=f"AR{overdue_days}",
            bill_date=bill_date,
            due_date=bill_date,
            bill_amount=Decimal("1000"),
            received_amount=Decimal("0"),
            is_overdue=is_overdue,
            overdue_days=overdue_days,
            company_code="C001",
        )


class TestRiskLevelCalculator:
    def setup_method(self):
        self.calc = RiskLevelCalculator()

    def test_high_risk_overdue_rate_above_30_percent(self):
        level = self.calc.calculate(score=50.0, overdue_rate=0.35)
        assert level == "高"

    def test_high_risk_low_score(self):
        level = self.calc.calculate(score=30.0, overdue_rate=0.1)
        assert level == "高"

    def test_medium_risk(self):
        level = self.calc.calculate(score=60.0, overdue_rate=0.15)
        assert level == "中"

    def test_low_risk(self):
        level = self.calc.calculate(score=80.0, overdue_rate=0.05)
        assert level == "低"


class TestCustomer360Generator:
    def setup_method(self):
        self.gen = Customer360Generator()

    def test_generate_from_auto_merge(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯科技")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯科技")
        match = MatchResult(
            action=MatchAction.AUTO_MERGE,
            customers=[c1, c2],
            unified_customer_code="C360_abc123",
            similarity=1.0,
            reason="名称完全相同",
        )
        records = self.gen.generate_from_match([match], stat_date=date(2025, 3, 21))
        assert len(records) == 1
        assert records[0].unified_customer_code == "C360_abc123"
        assert records[0].merge_status == "auto_merged"

    def test_generate_from_pending(self):
        c1 = RawCustomer(source_system="kingdee", customer_id="K001", customer_name="腾讯科技")
        c2 = RawCustomer(source_system="kingdee", customer_id="K002", customer_name="腾讯科技（深圳）")
        match = MatchResult(
            action=MatchAction.PENDING,
            customers=[c1, c2],
            similarity=0.91,
            reason="名称相似度 0.91",
        )
        records = self.gen.generate_from_match([match], stat_date=date(2025, 3, 21))
        assert len(records) == 0  # pending 不生成 360 记录
```

- [ ] **Step 2: 运行测试确认失败（模块不存在）**

Run: `uv run pytest tests/unit/test_customer360_service.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 创建 services/customer360_service.py**

```python
# services/customer360_service.py
"""客户360核心业务服务"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schemas.customer360 import (
    Customer360Record,
    Customer360Summary,
    CustomerDistribution,
    CustomerMergeQueue,
    CustomerTrend,
    MatchAction,
    MatchResult,
    MergeHistory,
    RawARRecord,
    RawCustomer,
)
from services.clickhouse_service import ClickHouseDataService
from services.customer_matcher import CustomerMatcher
from services.customer_standardizer import CustomerStandardizer

logger = logging.getLogger(__name__)


# --- 评分计算 ---

class PaymentScoreCalculator:
    """付款信用分计算器（0-100分）"""

    def calculate(self, ar_records: list[RawARRecord]) -> float:
        if not ar_records:
            return 50.0

        score = 100.0

        # 逾期率扣分：每 1% 逾期率扣 2 分
        overdue_count = sum(1 for r in ar_records if r.is_overdue)
        overdue_rate = overdue_count / len(ar_records)
        score -= overdue_rate * 200

        # 超长账龄扣分：超90天占比 > 30% 扣 10 分
        long_aging = sum(1 for r in ar_records if r.overdue_days > 90)
        if long_aging / len(ar_records) > 0.3:
            score -= 10

        # 近期付款加分：90天内已付款占比 > 70% 加 5 分
        recent_paid = sum(
            1 for r in ar_records
            if not r.is_overdue
            and (date.today() - r.bill_date).days < 90
        )
        if recent_paid / len(ar_records) > 0.7:
            score += 5

        # 合作时长加分：首次合作 > 2年 加 5 分
        if ar_records:
            bill_dates = [r.bill_date for r in ar_records]
            earliest = min(bill_dates)
            if (date.today() - earliest).days > 730:  # 2 * 365
                score += 5

        return max(0.0, min(100.0, score))


class RiskLevelCalculator:
    """风险等级计算器"""

    def calculate(self, score: float, overdue_rate: float) -> str:
        if overdue_rate > 0.3 or score < 40:
            return "高"
        elif overdue_rate > 0.1 or score < 70:
            return "中"
        return "低"


# --- 360 记录生成 ---

class Customer360Generator:
    """客户360记录生成器"""

    def __init__(
        self,
        score_calc: PaymentScoreCalculator | None = None,
        risk_calc: RiskLevelCalculator | None = None,
    ):
        self._score_calc = score_calc or PaymentScoreCalculator()
        self._risk_calc = risk_calc or RiskLevelCalculator()

    def generate_from_match(
        self,
        matches: list[MatchResult],
        ar_by_customer: dict[str, list[RawARRecord]] | None = None,
        stat_date: date | None = None,
    ) -> list[Customer360Record]:
        """从匹配结果生成 360 记录（仅处理 auto_merge）"""
        records: list[Customer360Record] = []
        ar_by_customer = ar_by_customer or {}
        stat_date = stat_date or date.today()

        for match in matches:
            if match.action != MatchAction.AUTO_MERGE:
                continue

            customers = match.customers
            unified_code = match.unified_customer_code or ""

            # 聚合应收数据
            all_ar: list[RawARRecord] = []
            for c in customers:
                all_ar.extend(ar_by_customer.get(c.customer_id, []))

            ar_total = sum((r.bill_amount for r in all_ar), Decimal("0"))
            ar_overdue = sum((r.bill_amount for r in all_ar if r.is_overdue), Decimal("0"))
            overdue_rate = float(ar_overdue / ar_total) if ar_total > 0 else 0.0
            payment_score = self._score_calc.calculate(all_ar)
            risk_level = self._risk_calc.calculate(payment_score, overdue_rate)

            # 计算 last_payment_date（已付款记录中的最近付款日期）和 first_coop_date（最早期应收日期）
            if all_ar:
                paid_dates = [r.bill_date for r in all_ar if not r.is_overdue]
                all_dates = [r.bill_date for r in all_ar]
                last_payment_date = min(paid_dates) if paid_dates else None
                first_coop_date = min(all_dates)
                # 取金额最大的应收记录对应的 company_code 作为主公司
                company_code = max(all_ar, key=lambda r: float(r.bill_amount)).company_code
            else:
                last_payment_date = None
                first_coop_date = None
                company_code = None

            # 合并客户名称（取最长的规范化名称）
            customer_name = max((c.customer_name for c in customers), key=len)
            customer_short_name = customers[0].customer_short_name

            records.append(
                Customer360Record(
                    unified_customer_code=unified_code,
                    raw_customer_ids=[c.customer_id for c in customers],
                    source_systems=[c.source_system for c in customers],
                    customer_name=customer_name,
                    customer_short_name=customer_short_name,
                    ar_total=ar_total,
                    ar_overdue=ar_overdue,
                    overdue_rate=overdue_rate,
                    payment_score=payment_score,
                    risk_level=risk_level,
                    merge_status="auto_merged",
                    last_payment_date=last_payment_date,
                    first_coop_date=first_coop_date,
                    company_code=company_code,
                    stat_date=stat_date,
                    updated_at=datetime.now(),
                )
            )

        return records


# --- 主服务 ---

class Customer360Service:
    """客户360主服务

    整合：连接器 → 标准化 → 匹配 → 360生成 → ClickHouse持久化
    """

    def __init__(
        self,
        ch_service: ClickHouseDataService | None = None,
    ):
        from api.dependencies import get_clickhouse_service

        self._ch = ch_service or get_clickhouse_service()
        self._standardizer = CustomerStandardizer()
        self._matcher = CustomerMatcher()
        self._generator = Customer360Generator()

    def refresh(self, stat_date: date | None = None) -> dict[str, Any]:
        """执行全量刷新（每日批次调用）"""
        stat_date = stat_date or date.today()
        results: dict[str, Any] = {"stat_date": str(stat_date), "errors": []}

        # 步骤1: 拉取客户
        try:
            from connectors.customer import ERPCustomerConnectorRegistry

            raw_customers = ERPCustomerConnectorRegistry.fetch_all_customers()
            results["customers_fetched"] = len(raw_customers)
        except Exception as e:
            logger.error(f"拉取客户数据失败: {e}")
            results["errors"].append(f"fetch_customers: {e}")
            return results

        # 步骤2: 标准化
        std_customers = [self._standardizer.standardize(c) for c in raw_customers]
        results["customers_standardized"] = len(std_customers)

        # 步骤3: 匹配
        matches = self._matcher.match(std_customers)
        results["auto_merges"] = len([m for m in matches if m.action == MatchAction.AUTO_MERGE])
        results["pending"] = len([m for m in matches if m.action == MatchAction.PENDING])

        # 步骤4: 写入合并队列并发送飞书通知
        try:
            pending = [m for m in matches if m.action == MatchAction.PENDING]
            self._upsert_merge_queue(pending)
            if pending:
                from services.feishu.feishu_client import FeishuClient
                feishu = FeishuClient()
                queue_items = self._ch.get_merge_queue("pending")
                feishu.send_merge_notification(queue_items)
        except Exception as e:
            logger.error(f"写入合并队列/飞书通知失败: {e}")
            results["errors"].append(f"merge_queue: {e}")

        # 步骤5: 生成并持久化 360 记录
        try:
            records = self._generator.generate_from_match(matches, stat_date=stat_date)
            self._ch.insert_customer360(records)
            results["records_persisted"] = len(records)
        except Exception as e:
            logger.error(f"持久化360记录失败: {e}")
            results["errors"].append(f"persist: {e}")

        return results

    def _upsert_merge_queue(self, pending_matches: list[MatchResult]) -> None:
        """将待复核匹配写入 ClickHouse merge_queue 表"""
        items = [
            CustomerMergeQueue(
                id=f"mq_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}",
                match_result=m,
            )
            for i, m in enumerate(pending_matches)
        ]
        if items:
            self._ch.insert_merge_queue(items)

    def get_summary(self, stat_date: date | None = None) -> Customer360Summary:
        """获取管理层汇总数据"""
        return self._ch.get_customer360_summary(stat_date or date.today())

    def get_distribution(self, stat_date: date | None = None) -> CustomerDistribution:
        """获取客户分布数据"""
        return self._ch.get_customer360_distribution(stat_date or date.today())

    def get_trend(self, months: int = 12) -> CustomerTrend:
        """获取客户/应收趋势"""
        return self._ch.get_customer360_trend(months)

    def get_customer_detail(self, unified_code: str) -> dict[str, Any]:
        """获取单个客户详情"""
        return self._ch.get_customer360_detail(unified_code)

    def get_merge_queue(self, status: str = "pending") -> list[CustomerMergeQueue]:
        """获取合并复核队列"""
        return self._ch.get_merge_queue(status)

    def confirm_merge(self, queue_id: str, operator: str = "system") -> dict[str, Any]:
        """确认合并"""
        return self._ch.confirm_merge(queue_id, operator)

    def reject_merge(self, queue_id: str, operator: str = "system") -> dict[str, Any]:
        """拒绝合并"""
        return self._ch.reject_merge(queue_id, operator)

    def undo_merge(
        self,
        unified_customer_code: str,
        original_customer_id: str,
        operator: str = "system",
        reason: str = "",
    ) -> dict[str, Any]:
        """撤销合并"""
        return self._ch.undo_merge(unified_customer_code, original_customer_id, operator, reason)

    def get_attribution_data(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """AI 归因数据接口"""
        return self._ch.get_customer_attribution(start_date, end_date)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_customer360_service.py -v`
Expected: PASS（6 tests）

- [ ] **Step 5: Commit**

```bash
git add services/customer360_service.py tests/unit/test_customer360_service.py
git commit -m "feat: add Customer360Service with scoring and matching integration"
```

---

## Task 7: ClickHouse DDL + 服务扩展

**Files:**
- Create: `scripts/customer360_ddl.sql`
- Modify: `services/clickhouse_service.py`

- [ ] **Step 1: 创建 ClickHouse DDL 脚本**

```sql
-- scripts/customer360_ddl.sql
-- Phase 4B 客户360相关表的 DDL
-- 执行方式: clickhouse-client --queries-file=scripts/customer360_ddl.sql

-- raw_customer: 标准化客户原始记录（ReplacingMergeTree，同主键去重）
CREATE TABLE IF NOT EXISTS raw.raw_customer (
    id              String,
    source_system   String,
    customer_id     String,
    customer_name   String,
    customer_short_name String,
    tax_id          String,
    credit_code     String,
    address         String,
    contact         String,
    phone           String,
    etl_time        DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(etl_time)
ORDER BY (source_system, customer_id);

-- dm_customer360: 客户360事实表（ReplacingMergeTree，每日快照覆盖更新）
CREATE TABLE IF NOT EXISTS dm.dm_customer360 (
    unified_customer_code  String,
    raw_customer_ids       Array(String),
    source_systems         Array(String),
    customer_name          String,
    customer_short_name    String,
    ar_total               Decimal(18, 2),
    ar_overdue             Decimal(18, 2),
    overdue_rate           Float32,
    payment_score          Float32,
    risk_level             String,
    merge_status           String,
    last_payment_date      Date,
    first_coop_date       Date,
    company_code          String,  -- 用于按公司维度分布统计
    stat_date              Date,
    updated_at             DateTime,
    PRIMARY KEY (unified_customer_code, stat_date)
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (unified_customer_code, stat_date);

-- customer_merge_queue: 合并复核队列
CREATE TABLE IF NOT EXISTS dm.customer_merge_queue (
    id              String,
    action          String,          -- auto_merge / pending
    similarity      Float32,
    reason          String,
    customer_ids    Array(String),
    customer_names  Array(String),
    unified_customer_code String,   -- auto_merge 时填充
    status          String,          -- pending / confirmed / rejected / auto_merged
    operator        String,
    operated_at     DateTime,
    undo_record_id  String,
    created_at      DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (status, created_at);

-- merge_history: 合并历史（可逆操作记录）
CREATE TABLE IF NOT EXISTS dm.merge_history (
    id                      String,
    unified_customer_code   String,
    source_system           String,
    original_customer_id    String,
    operated_at             DateTime,
    operator                String,
    undo_record_id          String,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(operated_at)
ORDER BY (unified_customer_code, operated_at);
```

- [ ] **Step 2: 扩展 ClickHouseDataService（添加客户360相关方法）**

在 `services/clickhouse_service.py` 末尾添加以下方法（需要先读取完整文件确认行号）：

```python
# --- 客户360相关方法（Phase 4B） ---

def insert_customer360(self, records: list[Customer360Record]) -> int:
    """批量写入客户360记录"""
    if not records:
        return 0
    sql = """
    INSERT INTO dm.dm_customer360 (
        unified_customer_code, raw_customer_ids, source_systems,
        customer_name, customer_short_name,
        ar_total, ar_overdue, overdue_rate, payment_score,
        risk_level, merge_status,
        last_payment_date, first_coop_date, company_code,
        stat_date, updated_at
    ) VALUES
    """
    values = [
        (
            r.unified_customer_code,
            r.raw_customer_ids,
            r.source_systems,
            r.customer_name,
            r.customer_short_name or "",
            float(r.ar_total),
            float(r.ar_overdue),
            r.overdue_rate,
            r.payment_score,
            r.risk_level,
            r.merge_status,
            r.last_payment_date,
            r.first_coop_date,
            r.company_code or "",
            r.stat_date,
            r.updated_at,
        )
        for r in records
    ]
    self.execute(sql, values)
    return len(records)


def insert_merge_queue(self, items: list[CustomerMergeQueue]) -> int:
    """写入合并复核队列"""
    if not items:
        return 0
    sql = """
    INSERT INTO dm.customer_merge_queue (
        id, action, similarity, reason,
        customer_ids, customer_names, unified_customer_code,
        status, operator, operated_at, undo_record_id, created_at
    ) VALUES
    """
    values = [
        (
            item.id,
            item.match_result.action.value,
            item.match_result.similarity,
            item.match_result.reason,
            [c.customer_id for c in item.match_result.customers],
            [c.customer_name for c in item.match_result.customers],
            item.match_result.unified_customer_code or "",
            item.status,
            item.operator or "",
            item.operated_at,
            item.undo_record_id or "",
            item.match_result.created_at,
        )
        for item in items
    ]
    self.execute(sql, values)
    return len(items)


def get_customer360_summary(self, stat_date: date) -> Customer360Summary:
    """管理层汇总"""
    sql = """
    SELECT
        uniqExact(unified_customer_code)                           AS total_customers,
        sum(merge_status IN ('auto_merged', 'confirmed'))          AS merged_customers,
        sum(merge_status = 'pending')                              AS pending_merges,
        sum(ar_total)                                              AS ar_total,
        sum(ar_overdue)                                           AS ar_overdue_total,
        sum(ar_overdue) / sum(ar_total)                           AS overall_overdue_rate,
        sum(risk_level = '高')                                     AS risk_high,
        sum(risk_level = '中')                                     AS risk_mid,
        sum(risk_level = '低')                                     AS risk_low
    FROM dm.dm_customer360
    WHERE stat_date = %s
    """
    row = self.query_one(sql, (stat_date,))

    # 计算前10客户集中度（子查询）
    top10_sql = """
    SELECT sum(ar_total) AS top10_ar
    FROM (
        SELECT ar_total FROM dm.dm_customer360
        WHERE stat_date = %s
        ORDER BY ar_total DESC LIMIT 10
    )
    """
    top10_row = self.query_one(top10_sql, (stat_date,))
    total_ar = float(row["ar_total"]) if row["ar_total"] else 0.0
    top10_ar = float(top10_row["top10_ar"]) if top10_row and top10_row["top10_ar"] else 0.0
    concentration = (top10_ar / total_ar) if total_ar > 0 else 0.0

    return Customer360Summary(
        total_customers=row["total_customers"],
        merged_customers=row["merged_customers"],
        pending_merges=row["pending_merges"],
        ar_total=Decimal(str(row["ar_total"])),
        ar_overdue_total=Decimal(str(row["ar_overdue_total"])),
        overall_overdue_rate=float(row["overall_overdue_rate"]) * 100,  # 转为百分比
        risk_distribution={"高": row["risk_high"], "中": row["risk_mid"], "低": row["risk_low"]},
        concentration_top10_ratio=concentration,
    )


def get_customer360_distribution(self, stat_date: date) -> CustomerDistribution:
    """客户分布"""
    by_company_sql = """
    SELECT company_code AS company, count() AS count, sum(ar_total) AS ar_total
    FROM dm.dm_customer360 t
    WHERE stat_date = %s
    GROUP BY company_code ORDER BY ar_total DESC LIMIT 20
    """
    by_risk_sql = """
    SELECT risk_level AS risk, count() AS count, sum(ar_total) AS ar_total
    FROM dm.dm_customer360
    WHERE stat_date = %s
    GROUP BY risk_level
    """
    by_company = [dict(row) for row in self.query(by_company_sql, (stat_date,))]
    by_risk = [dict(row) for row in self.query(by_risk_sql, (stat_date,))]
    return CustomerDistribution(
        by_company=by_company,
        by_risk_level=by_risk,
        by_overdue_bucket=[{"bucket": "0-30天", "count": 0, "amount": 0.0}],  # TODO(实施): 从 dm.dm_customer360 或原始 AR 表按逾期天数分桶
    )


def get_customer360_trend(self, months: int = 12) -> CustomerTrend:
    """客户/应收趋势"""
    sql = """
    SELECT
        toYYYYMM(stat_date) AS ym,
        uniqExact(unified_customer_code) AS customer_count,
        sum(ar_total) AS ar_total,
        sum(ar_overdue) / sum(ar_total) AS overdue_rate
    FROM dm.dm_customer360
    WHERE stat_date >= today() - INTERVAL %s MONTH
    GROUP BY ym
    ORDER BY ym
    """
    rows = self.query(sql, (months,))
    return CustomerTrend(
        dates=[str(r["ym"]) for r in rows],
        customer_counts=[r["customer_count"] for r in rows],
        ar_totals=[float(r["ar_total"]) for r in rows],
        overdue_rates=[float(r["overdue_rate"]) for r in rows],
    )


def get_customer360_detail(self, unified_code: str) -> dict[str, Any]:
    """客户详情（包含账龄分布和最近应收单）"""
    # 主记录
    sql = """
    SELECT * FROM dm.dm_customer360
    WHERE unified_customer_code = %s
    ORDER BY stat_date DESC LIMIT 1
    """
    row = self.query_one(sql, (unified_code,))
    if not row:
        return {}

    detail = dict(row)

    # 账龄分布（从 raw_customer_ids 关联原始 AR 数据）
    aging_sql = """
    SELECT
        sumIf(bill_amount, overdue_days <= 30)   AS bucket_0_30,
        sumIf(bill_amount, overdue_days > 30 AND overdue_days <= 60)  AS bucket_31_60,
        sumIf(bill_amount, overdue_days > 60 AND overdue_days <= 90)  AS bucket_61_90,
        sumIf(bill_amount, overdue_days > 90)    AS bucket_90_plus
    FROM raw.ar_detail  -- TODO(实施): 替换为实际 AR 明细表名
    WHERE customer_id IN (%s)
      AND bill_date = toDate('%s')
    """
    # 占位：raw_customer_ids 用逗号拼接
    customer_ids = ",".join(f"'{cid}'" for cid in row["raw_customer_ids"])
    stat_d = row["stat_date"]
    aging_row = self.query_one(
        aging_sql % (customer_ids, stat_d),
        tuple(),
    )
    detail["aging_distribution"] = {
        "0-30天": float(aging_row["bucket_0_30"]) if aging_row else 0.0,
        "31-60天": float(aging_row["bucket_31_60"]) if aging_row else 0.0,
        "61-90天": float(aging_row["bucket_61_90"]) if aging_row else 0.0,
        "90天以上": float(aging_row["bucket_90_plus"]) if aging_row else 0.0,
    }

    # 最近应收单（最近5条）
    recent_sql = """
    SELECT bill_no, bill_amount, due_date, is_overdue, overdue_days
    FROM raw.ar_detail  -- TODO(实施): 替换为实际 AR 明细表名
    WHERE customer_id IN (%s)
    ORDER BY bill_date DESC LIMIT 5
    """
    recent_rows = self.query(recent_sql % (customer_ids), tuple())
    detail["recent_bills"] = [
        {
            "bill_no": r["bill_no"],
            "amount": float(r["bill_amount"]),
            "due_date": str(r["due_date"]),
            "status": "逾期" if r["is_overdue"] else "正常",
            "overdue_days": r["overdue_days"],
        }
        for r in recent_rows
    ]

    return detail


def get_merge_queue(self, status: str = "pending") -> list[CustomerMergeQueue]:
    """获取合并队列"""
    sql = """
    SELECT * FROM dm.customer_merge_queue
    WHERE status = %s
    ORDER BY created_at DESC
    """
    rows = self.query(sql, (status,))
    # 注意：实际实现需要反序列化 CustomerMergeQueue
    return [self._row_to_merge_queue(r) for r in rows]


def _row_to_merge_queue(self, row: dict) -> CustomerMergeQueue:
    """将数据库行反序列化为 CustomerMergeQueue"""
    # 简化实现，实际根据字段构建对象
    customers = [
        RawCustomer(
            source_system=row["source_systems"][i] if i < len(row["source_systems"]) else "kingdee",
            customer_id=row["customer_ids"][i],
            customer_name=row["customer_names"][i],
        )
        for i in range(len(row["customer_ids"]))
    ]
    match = MatchResult(
        action=MatchAction(row["action"]),
        customers=customers,
        unified_customer_code=row["unified_customer_code"] or None,
        similarity=row["similarity"],
        reason=row["reason"],
    )
    return CustomerMergeQueue(
        id=row["id"],
        match_result=match,
        status=row["status"],
        operator=row["operator"] or None,
        operated_at=row["operated_at"],
        undo_record_id=row["undo_record_id"] or None,
    )


def confirm_merge(self, queue_id: str, operator: str) -> dict[str, Any]:
    """确认合并：更新队列状态 + 更新 dm_customer360 对应记录的 merge_status"""
    # 1. 获取队列项以获取 unified_customer_code
    queue_row = self.query_one(
        "SELECT unified_customer_code FROM dm.customer_merge_queue WHERE id = %s",
        (queue_id,),
    )
    if not queue_row:
        return {"id": queue_id, "status": "not_found"}

    unified_code = queue_row["unified_customer_code"]

    # 2. 更新队列状态
    self.execute(
        "UPDATE dm.customer_merge_queue SET status = 'confirmed', operator = %s, operated_at = now() WHERE id = %s",
        (operator, queue_id),
    )

    # 3. 更新 dm_customer360 中该客户的 merge_status（从 pending → confirmed）
    # 注意：dm_customer360 使用 ReplacingMergeTree(updated_at)，
    # ALTER TABLE...UPDATE 为异步操作，变更在后台合并时生效，实时查询可能短暂不一致。
    if unified_code:
        today = date.today()
        self.execute(
            "ALTER TABLE dm.dm_customer360 UPDATE merge_status = 'confirmed', updated_at = now() "
            "WHERE unified_customer_code = %s AND stat_date = %s AND merge_status = 'pending'",
            (unified_code, today),
        )

    return {"id": queue_id, "status": "confirmed", "unified_customer_code": unified_code, "operator": operator}


def reject_merge(self, queue_id: str, operator: str) -> dict[str, Any]:
    """拒绝合并"""
    sql = """
    UPDATE dm.customer_merge_queue
    SET status = 'rejected', operator = %s, operated_at = now()
    WHERE id = %s AND status = 'pending'
    """
    self.execute(sql, (operator, queue_id))
    return {"id": queue_id, "status": "rejected", "operator": operator}


def undo_merge(
    self,
    unified_customer_code: str,
    original_customer_id: str,
    operator: str,
    reason: str,
) -> dict[str, Any]:
    """撤销合并"""
    import uuid
    undo_id = str(uuid.uuid4())
    sql = """
    INSERT INTO dm.merge_history (
        id, unified_customer_code, source_system, original_customer_id,
        operated_at, operator, undo_record_id
    ) VALUES
    """
    self.execute(sql, [(undo_id, unified_customer_code, "kingdee", original_customer_id, datetime.now(), operator, "")])
    return {"undo_id": undo_id, "unified_customer_code": unified_customer_code}


def get_customer_attribution(
    self,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """AI 归因数据（含期初/期末对比 delta）"""
    # 期末快照
    curr_sql = """
    SELECT
        unified_customer_code AS customer_code,
        customer_name,
        ar_overdue AS ar_overdue_curr,
        ar_total AS ar_total_curr,
        overdue_rate AS overdue_rate_curr,
        risk_level
    FROM dm.dm_customer360
    WHERE stat_date = %s
    ORDER BY ar_overdue DESC
    LIMIT 200
    """
    curr_rows = self.query(curr_sql, (end_date,))
    if not curr_rows:
        return {"dimension": "customer", "data": []}

    # 期初快照（用于计算 delta）
    prev_sql = """
    SELECT
        unified_customer_code AS customer_code,
        ar_overdue AS ar_overdue_prev,
        overdue_rate AS overdue_rate_prev
    FROM dm.dm_customer360
    WHERE stat_date = %s
    """
    prev_map = {r["customer_code"]: r for r in self.query(prev_sql, (start_date,))}

    # 合并期初/期末，计算 delta
    data = []
    for row in curr_rows:
        code = row["customer_code"]
        prev = prev_map.get(code, {})
        ar_prev = float(prev.get("ar_overdue_prev") or 0.0)
        rate_prev = float(prev.get("overdue_rate_prev") or 0.0)
        ar_curr = float(row["ar_overdue_curr"])
        rate_curr = float(row["overdue_rate_curr"])
        data.append({
            "customer_code": code,
            "customer_name": row["customer_name"],
            "ar_overdue_curr": ar_curr,
            "ar_overdue_prev": ar_prev,
            "overdue_delta": ar_curr - ar_prev,
            "overdue_rate_curr": rate_curr,
            "overdue_rate_prev": rate_prev,
            "risk_level": row["risk_level"],
        })

    data.sort(key=lambda x: x["overdue_delta"], reverse=True)
    return {
        "dimension": "customer",
        "data": data,
    }
```

- [ ] **Step 3: Commit**

```bash
git add scripts/customer360_ddl.sql
git commit -m "feat: add customer360 ClickHouse DDL"
```

**注意**: `services/clickhouse_service.py` 的扩展需要编辑现有文件，在末尾添加上述方法。先读取文件确认末尾行号再添加。

---

## Task 8: 调度服务（APScheduler）

**Files:**
- Create: `services/scheduler_service.py`
- Modify: `api/main.py`

- [ ] **Step 1: 创建调度服务**

```python
# services/scheduler_service.py
"""客户360每日调度服务"""
import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.customer360_service import Customer360Service

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def daily_customer360_job() -> None:
    """每日02:00执行的客户360刷新任务"""
    logger.info("开始执行客户360每日刷新...")
    try:
        service = Customer360Service()
        result = service.refresh(stat_date=date.today())
        logger.info(f"客户360刷新完成: {result}")
    except Exception as e:
        logger.error(f"客户360刷新失败: {e}", exc_info=True)


def start_scheduler() -> AsyncIOScheduler:
    """启动 APScheduler（仅在非测试环境）"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    import os
    if os.environ.get("TESTING") == "1":
        logger.debug("测试环境，跳过调度器启动")
        return _scheduler

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        daily_customer360_job,
        "cron",
        hour=2,
        minute=0,
        id="customer360_daily",
        name="客户360每日刷新",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("APScheduler 已启动，客户360每日刷新任务已注册（02:00）")
    return _scheduler


def stop_scheduler() -> None:
    """停止调度器"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("APScheduler 已停止")
```

- [ ] **Step 2: 在 api/main.py 启动时注册调度器**

在 `api/main.py` 中找到 `if __name__ == "__main__":` 或 `app = FastAPI()` 附近，添加：

```python
# 在 uvicorn 启动时同时启动调度器
@app.on_event("startup")
async def startup_event():
    from services.scheduler_service import start_scheduler
    start_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    from services.scheduler_service import stop_scheduler
    stop_scheduler()
```

- [ ] **Step 3: Commit**

```bash
git add services/scheduler_service.py
# 修改 api/main.py 时需要读取文件后编辑
git commit -m "feat: add APScheduler daily customer360 refresh job"
```

---

## Task 9: API 路由 + 依赖注入

**Files:**
- Create: `api/routes/customer360.py`
- Create: `api/schemas/customer360.py`
- Modify: `api/dependencies.py`
- Modify: `api/main.py`

- [ ] **Step 1: 创建 API schemas**

```python
# api/schemas/customer360.py
"""客户360 API 请求/响应模型"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class Customer360SummaryResponse(BaseModel):
    total_customers: int
    merged_customers: int
    pending_merges: int
    ar_total: float
    ar_overdue_total: float
    overall_overdue_rate: float
    risk_distribution: dict[str, int]
    concentration_top10_ratio: float


class MergeQueueItemResponse(BaseModel):
    id: str
    similarity: float
    reason: str
    customers: list[dict[str, str]]
    unified_customer_code: str | None = None
    status: Literal["pending", "confirmed", "rejected", "auto_merged"]
    created_at: datetime


class MergeQueueResponse(BaseModel):
    items: list[MergeQueueItemResponse]
    total: int


class ConfirmActionRequest(BaseModel):
    action: Literal["confirm"] = "confirm"


class RejectActionRequest(BaseModel):
    action: Literal["reject"] = "reject"


class UndoMergeRequest(BaseModel):
    original_customer_id: str
    reason: str = ""


class AttributionDataResponse(BaseModel):
    dimension: str
    data: list[dict[str, Any]]
```

- [ ] **Step 2: 创建 API 路由**

```python
# api/routes/customer360.py
"""客户360 API 路由"""
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import Customer360ServiceDep
from api.schemas.customer360 import (
    AttributionDataResponse,
    ConfirmActionRequest,
    MergeQueueResponse,
    RejectActionRequest,
    UndoMergeRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/customer360", tags=["客户360"])


@router.get("/summary", response_model=dict)
async def get_customer360_summary(service: Customer360ServiceDep):
    """管理层视角客户汇总"""
    try:
        return service.get_summary()
    except Exception as e:
        logger.error(f"获取客户360汇总失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/distribution", response_model=dict)
async def get_customer360_distribution(
    service: Customer360ServiceDep,
    stat_date: str | None = Query(None, description="统计日期 YYYY-MM-DD"),
):
    """客户分布数据（用于图表）"""
    try:
        d = date.fromisoformat(stat_date) if stat_date else date.today()
        return service.get_distribution(d)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的日期格式，请使用 YYYY-MM-DD")
    except Exception as e:
        logger.error(f"获取客户分布失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trend", response_model=dict)
async def get_customer360_trend(
    service: Customer360ServiceDep,
    months: int = Query(12, ge=1, le=24, description="查询月数"),
):
    """客户/应收趋势（近N个月）"""
    try:
        return service.get_trend(months)
    except Exception as e:
        logger.error(f"获取趋势数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{customer_code}/detail", response_model=dict)
async def get_customer_detail(
    customer_code: str,
    service: Customer360ServiceDep,
):
    """单个客户360详情"""
    detail = service.get_customer_detail(customer_code)
    if not detail:
        raise HTTPException(status_code=404, detail="客户不存在")
    return detail


@router.get("/merge-queue", response_model=MergeQueueResponse)
async def get_merge_queue(
    service: Customer360ServiceDep,
    status: str = Query("pending", description="筛选状态"),
):
    """合并复核队列"""
    items = service.get_merge_queue(status)
    return MergeQueueResponse(
        items=[
            {
                "id": item.id,
                "similarity": item.match_result.similarity,
                "reason": item.match_result.reason,
                "customers": [
                    {"customer_id": c.customer_id, "name": c.customer_name, "source": c.source_system}
                    for c in item.match_result.customers
                ],
                "unified_customer_code": item.match_result.unified_customer_code,
                "status": item.status,
                "created_at": item.match_result.created_at,
            }
            for item in items
        ],
        total=len(items),
    )


@router.post("/merge-queue/{queue_id}/confirm")
async def confirm_merge(
    queue_id: str,
    service: Customer360ServiceDep,
):
    """确认合并"""
    result = service.confirm_merge(queue_id)
    return result


@router.post("/merge-queue/{queue_id}/reject")
async def reject_merge(
    queue_id: str,
    service: Customer360ServiceDep,
):
    """拒绝合并"""
    result = service.reject_merge(queue_id)
    return result


@router.post("/{customer_code}/undo")
async def undo_merge(
    customer_code: str,
    request: UndoMergeRequest,
    service: Customer360ServiceDep,
):
    """撤销合并"""
    result = service.undo_merge(
        unified_customer_code=customer_code,
        original_customer_id=request.original_customer_id,
        reason=request.reason,
    )
    return result


@router.get("/attribution", response_model=AttributionDataResponse)
async def get_attribution_data(
    service: Customer360ServiceDep,
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
):
    """AI 归因数据接口"""
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的日期格式")
    return service.get_attribution_data(sd, ed)
```

- [ ] **Step 3: 更新 api/dependencies.py**

在 `api/dependencies.py` 中添加：

```python
from services.customer360_service import Customer360Service

@lru_cache
def get_customer360_service() -> Customer360Service:
    """获取客户360服务实例（单例）"""
    return Customer360Service()

# 添加类型别名
Customer360ServiceDep = Annotated[Customer360Service, Depends(get_customer360_service)]
```

- [ ] **Step 4: 在 api/main.py 注册路由**

在 `api/main.py` 中找到路由注册区域，添加：

```python
from api.routes.customer360 import router as customer360_router

# 在 app.include_router 部分添加：
app.include_router(customer360_router, prefix="/api/v1")
```

- [ ] **Step 5: Commit**

```bash
git add api/routes/customer360.py api/schemas/customer360.py api/dependencies.py api/main.py
git commit -m "feat: add customer360 API routes"
```

---

## Task 10: 飞书合并通知

**Files:**
- Modify: `services/feishu/feishu_client.py`
- Modify: `api/config.py`

- [ ] **Step 1: 更新 FeishuConfig 添加运营渠道 ID**

在 `api/config.py` 的 `FeishuConfig` 类中添加：

```python
ops_channel_id: str = Field(default="", description="运营通知飞书渠道ID（群机器人或用户OpenID）")
```

- [ ] **Step 2: 添加飞书合并通知方法**

在 `services/feishu/feishu_client.py` 中添加：

```python
def send_merge_notification(self, queue_items: list) -> bool:
    """发送合并复核通知卡片

    Args:
        queue_items: 待复核的合并队列项列表（CustomerMergeQueue）
    Returns:
        是否发送成功
    """
    config = get_feishu_config()
    if not config.ops_channel_id:
        import logging
        logging.getLogger(__name__).warning("FEISHU_OPS_CHANNEL_ID 未配置，跳过飞书通知")
        return False

    from services.feishu.card_builder import build_merge_card

    success = True
    for item in queue_items:
        card = build_merge_card(item.match_result, queue_id=item.id)
        if not self.send_card_to_channel(card, channel_id=config.ops_channel_id):
            success = False
    return success


def send_card_to_channel(self, card: dict, channel_id: str) -> bool:
    """发送卡片到指定渠道（群机器人或用户）"""
    # channel_id 可以是 OpenID（发送给用户）或群机器人 webhook URL
    if channel_id.startswith("https://"):
        # webhook URL 方式
        return self._send_via_webhook(channel_id, card)
    # 飞书 OpenID 方式
    return self.send_card(receive_id=channel_id, card_content=card)


def _send_via_webhook(self, webhook_url: str, card: dict) -> bool:
    """通过 webhook 发送卡片"""
    import httpx
    card_json = {"config": {"wide_screen_mode": True}, "elements": card.get("elements", [])}
    with httpx.Client(timeout=10) as client:
        resp = client.post(webhook_url, json={"msg_type": "interactive", "content": card_json})
    return resp.status_code == 200
```

- [ ] **Step 3: 在 card_builder.py 添加 build_merge_card**

在 `services/feishu/card_builder.py` 中添加：

```python
def build_merge_card(match_result, queue_id: str | None = None) -> dict:
    """构建合并复核卡片

    Args:
        match_result: MatchResult 对象
        queue_id: 队列项 ID（来自 CustomerMergeQueue.id）
    """
    customers = match_result.customers
    card_id = queue_id or (customers[0].customer_id if customers else "unknown")
    return {
        "header": {
            "title": {"tag": "plain_text", "content": "🔔 客户合并待确认"},
            "template": "orange",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**发现 {len(customers)} 个疑似同一客户：**\n\n"
                    + "\n".join(f"- `{c.customer_id}` {c.customer_name}" for c in customers)
                    + f"\n\n**相似度**：{match_result.similarity:.0%}\n**原因**：{match_result.reason}"
                ),
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✅ 合并"},
                        "type": "primary",
                        "value": f'{{"action": "merge", "queue_id": "{card_id}"}}',
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "❌ 忽略"},
                        "type": "danger",
                        "value": f'{{"action": "reject", "queue_id": "{card_id}"}}',
                    },
                ],
            },
        ],
    }
```

- [ ] **Step 4: Commit**

```bash
git add services/feishu/feishu_client.py services/feishu/card_builder.py api/config.py
git commit -m "feat: add Feishu merge notification support"
```

---

## Task 11: 初始化脚本

**Files:**
- Create: `scripts/init_customer360.py`

- [ ] **Step 1: 创建初始化脚本**

```python
#!/usr/bin/env python
"""初始化客户360相关表和依赖配置"""
import sys
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    from services.clickhouse_service import ClickHouseDataService

    ch = ClickHouseDataService()

    # 读取 DDL 文件
    ddl_path = Path(__file__).parent / "customer360_ddl.sql"
    if not ddl_path.exists():
        logger.error(f"DDL 文件不存在: {ddl_path}")
        return

    with open(ddl_path) as f:
        ddl_content = f.read()

    # 逐条执行（ClickHouse 支持多语句）
    statements = [s.strip() for s in ddl_content.split(";") if s.strip()]
    for stmt in statements:
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            # 提取表名用于日志
            table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[-1].split("(")[0].strip()
            logger.info(f"  ✅ {table_name}")
        except Exception as e:
            logger.error(f"  ❌ 执行失败: {e}")

    logger.info("客户360初始化完成！")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/init_customer360.py
git commit -m "scripts: add customer360 init script"
```

---

## Task 12: 集成测试

**Files:**
- Create: `tests/integration/test_customer360_api.py`

- [ ] **Step 1: 写集成测试**

```python
# tests/integration/test_customer360_api.py
"""客户360 API 集成测试"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from schemas.customer360 import Customer360Summary


@pytest.fixture
def client():
    return TestClient(app)


class TestCustomer360SummaryAPI:
    def test_get_summary_returns_200(self, client):
        with patch(
            "services.customer360_service.Customer360Service.get_summary",
            return_value=Customer360Summary(
                total_customers=100,
                merged_customers=5,
                pending_merges=2,
                ar_total=1000000.00,
                ar_overdue_total=50000.00,
                overall_overdue_rate=5.0,
                risk_distribution={"高": 3, "中": 10, "低": 87},
                concentration_top10_ratio=0.35,
            ),
        ):
            response = client.get("/api/v1/customer360/summary")
            assert response.status_code == 200
            data = response.json()
            assert data["total_customers"] == 100
            assert data["merged_customers"] == 5


class TestMergeQueueAPI:
    def test_get_merge_queue_returns_200(self, client):
        with patch(
            "services.customer360_service.Customer360Service.get_merge_queue",
            return_value=[],
        ):
            response = client.get("/api/v1/customer360/merge-queue?status=pending")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert "total" in data
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/test_customer360_api.py
git commit -m "test: add customer360 integration tests"
```

---

## 执行顺序

```
Task 1 (依赖) → Task 2 (模型) → Task 3 (连接器) → Task 4 (标准化) → Task 5 (匹配)
→ Task 6 (核心服务) → Task 7 (ClickHouse) → Task 8 (调度) → Task 9 (API) → Task 10 (飞书) → Task 11 (脚本) → Task 12 (测试)
```

**前置要求**: Task 7 依赖 Task 2（schemas），Task 6 依赖 Task 3/4/5，Task 9 依赖 Task 6，Task 10 依赖 Task 6。
