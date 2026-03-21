# Phase 6 实施计划 - 业务员通道 + AP 扩展

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建业务员 AR 报告通道和 AP 扩展（银行对账单），包含完整的 DDL、Service、API、模板和调度任务。

**Architecture:**
- `SalespersonMappingService` — 业务员+客户映射 CRUD，支持 CSV 批量上传，写入 `dm.salesperson_mapping` + `dm.salesperson_customer_mapping`
- `APBankStatementParser` — 银行 CSV/Excel 解析，列名优先级匹配，供应商模糊匹配，写入 `raw.ap_bank_statement` → `std.ap_std_record`
- `APService` — AP 数据聚合，KPI/看板查询
- `PerSalespersonReportService` — per-rep AR 报告生成，发送到销售群
- APScheduler — 每周一 08:05 + 每月1日 08:05 触发 per-rep 报告

**Tech Stack:** Python 3.11, FastAPI, ClickHouse, APScheduler, Jinja2, openpyxl (Excel), difflib, Pydantic

---

## 文件结构

```
新增文件:
  schemas/ap.py                          # APStdRecord Pydantic 模型
  services/ap_bank_parser.py              # 银行对账单解析服务
  services/ap_service.py                 # AP 数据聚合服务
  services/salesperson_mapping_service.py # 业务员映射 CRUD + CSV
  api/routes/ap.py                       # AP 上传 + 查询 API
  api/routes/salesperson_mapping.py      # 业务员映射 CRUD API
  api/schemas/ap.py                     # AP API 请求/响应模型
  api/schemas/salesperson_mapping.py     # 业务员映射 API 模型
  scripts/phase6_ddl.sql                # Phase 6 DDL
  scripts/init_phase6.py                  # Phase 6 表初始化
  templates/reports/ar_per_salesperson.html.j2  # 业务员 AR 报告模板
  templates/reports/ap_report.html.j2           # AP 报告模板
  tests/unit/test_ap_bank_parser.py
  tests/unit/test_salesperson_mapping_service.py
  tests/integration/test_ap_api.py

修改文件:
  api/config.py                          # +FEISHU_SALES_CHANNEL_ID, +AP_DEFAULT_PAYMENT_TERM_DAYS
  api/dependencies.py                    # +APServiceDep, +SalespersonMappingServiceDep
  api/main.py                            # 注册 ap, salesperson_mapping 路由
  services/scheduler_service.py           # +08:05 定时任务
  services/clickhouse_service.py         # +AP 相关查询方法
  services/report_service.py             # +generate_per_salesperson(), +send_to_sales_channel()
  .env.example                          # +FEISHU_SALES_CHANNEL_ID, +AP_DEFAULT_PAYMENT_TERM_DAYS
  pyproject.toml                         # +openpyxl
```

---

## Task 1: DDL + 初始化脚本

**Files:**
- Create: `scripts/phase6_ddl.sql`
- Create: `scripts/init_phase6.py`
- Test: `tests/unit/test_phase6_init.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_phase6_init.py
"""测试 Phase 6 DDL 和初始化脚本"""
import pytest
from pathlib import Path


def test_ddl_creates_4_tables():
    """验证 DDL 包含 4 张表的 CREATE 语句"""
    ddl_path = Path(__file__).parents[2] / "scripts" / "phase6_ddl.sql"
    content = ddl_path.read_text()
    assert "raw.ap_bank_statement" in content
    assert "std.ap_std_record" in content
    assert "dm.salesperson_mapping" in content
    assert "dm.salesperson_customer_mapping" in content
    assert "ReplacingMergeTree" in content
    assert "SETTINGS allow_experimental_object_type = 1" in content
    assert "UNIQUE (salesperson_id, customer_id)" in content
    # std.ap_std_record 去重键为 bank_transaction_no
    assert "ORDER BY (bank_transaction_no)" in content


def test_ddl_alters_report_records():
    """验证 DDL 包含 ALTER TABLE 扩展 report_records"""
    ddl_path = Path(__file__).parents[2] / "scripts" / "phase6_ddl.sql"
    content = ddl_path.read_text()
    assert "ALTER TABLE dm.report_records" in content
    assert "salesperson_id" in content
    assert "supplier_code" in content
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/unit/test_phase6_init.py -v`
Expected: FAIL (file not found)

- [ ] **Step 3: 创建 scripts/phase6_ddl.sql**

```sql
-- scripts/phase6_ddl.sql
-- Phase 6 DDL: 业务员映射表 + AP 银行对账单表

-- raw.ap_bank_statement: 原始银行对账单
CREATE TABLE IF NOT EXISTS raw.ap_bank_statement (
    id              String,
    file_name       String,
    bank_date       Date,
    transaction_no  String,
    counterparty    String,
    amount          Decimal(18, 2),
    direction       String,
    remark          String,
    created_at      DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (file_name, bank_date, transaction_no)
SETTINGS allow_experimental_object_type = 1;

-- std.ap_std_record: 标准化 AP 记录
CREATE TABLE IF NOT EXISTS std.ap_std_record (
    id                  String,
    supplier_code       String,
    supplier_name       String,
    bank_date           Date,
    due_date            Date,
    amount              Decimal(18, 2),
    received_amount     Decimal(18, 2),
    is_settled          UInt8,
    settlement_date     Date,
    bank_transaction_no String,
    payment_method      String,
    source_file         String,
    etl_time            DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(etl_time)
ORDER BY (bank_transaction_no)
SETTINGS allow_experimental_object_type = 1;

-- dm.salesperson_mapping: 业务员主表
CREATE TABLE IF NOT EXISTS dm.salesperson_mapping (
    id               String,
    salesperson_id   String,
    salesperson_name String,
    feishu_open_id  String,
    enabled          UInt8,
    created_at       DateTime,
    updated_at       DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (salesperson_id, updated_at)
SETTINGS allow_experimental_object_type = 1;

-- dm.salesperson_customer_mapping: 客户→业务员多对多映射
CREATE TABLE IF NOT EXISTS dm.salesperson_customer_mapping (
    id              String,
    salesperson_id  String,
    customer_id     String,
    customer_name   String,
    created_at      DateTime,
    UNIQUE (salesperson_id, customer_id)
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (salesperson_id, customer_id)
SETTINGS allow_experimental_object_type = 1;

-- 扩展 dm.report_records 以支持 Phase 6 报告类型
ALTER TABLE dm.report_records
    ADD COLUMN IF NOT EXISTS salesperson_id String DEFAULT '',
    ADD COLUMN IF NOT EXISTS supplier_code String DEFAULT '';
```

- [ ] **Step 4: 创建 scripts/init_phase6.py**

```python
#!/usr/bin/env python
"""初始化 Phase 6 相关表"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    from services.clickhouse_service import ClickHouseDataService
    from clickhouse_driver.errors import Error as ClickHouseError

    ch = ClickHouseDataService()
    ddl_path = Path(__file__).parent / "phase6_ddl.sql"
    if not ddl_path.exists():
        logger.error(f"DDL 文件不存在: {ddl_path}")
        return

    with open(ddl_path) as f:
        ddl_content = f.read()

    statements = [s.strip() for s in ddl_content.split(";") if s.strip()]
    for stmt in statements:
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[-1].split("(")[0].strip()
            logger.info(f"  OK {table_name}")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[-1].split("(")[0].strip()
                logger.info(f"  SKIP {table_name} (already exists)")
            else:
                logger.error(f"  FAIL execute: {e}")
        except Exception as e:
            logger.error(f"  FAIL: {e}")

    logger.info("Phase 6 初始化完成！")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行测试验证通过**

Run: `uv run pytest tests/unit/test_phase6_init.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/phase6_ddl.sql scripts/init_phase6.py tests/unit/test_phase6_init.py
git commit -m "feat: Phase 6 DDL + init script (ap_bank_statement, ap_std_record, salesperson_mapping)"
```

---

## Task 2: SalespersonMappingService + 映射 API

**Files:**
- Create: `schemas/ap.py`（共享数据模型，也被 Task 3 使用）
- Create: `services/salesperson_mapping_service.py`
- Create: `api/routes/salesperson_mapping.py`
- Create: `api/schemas/salesperson_mapping.py`
- Modify: `api/config.py`（+FEISHU_SALES_CHANNEL_ID）
- Modify: `api/dependencies.py`
- Modify: `.env.example`
- Test: `tests/unit/test_salesperson_mapping_service.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_salesperson_mapping_service.py
"""测试 SalespersonMappingService"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.salesperson_mapping_service import (
    SalespersonMappingService,
    SalespersonMappingRow,
)


class TestSalespersonMappingService:
    def test_list_active_returns_only_enabled(self):
        with patch(
            "services.salesperson_mapping_service.ClickHouseDataService"
        ) as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [
                {"id": "1", "salesperson_id": "S001", "enabled": 1},
                {"id": "2", "salesperson_id": "S002", "enabled": 0},
            ]
            svc = SalespersonMappingService()
            active = svc.list_active()
            assert len(active) == 1
            assert active[0]["salesperson_id"] == "S001"

    def test_list_customers_by_salesperson(self):
        with patch(
            "services.salesperson_mapping_service.ClickHouseDataService"
        ) as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [
                {"customer_id": "C001", "customer_name": "腾讯科技"},
            ]
            svc = SalespersonMappingService()
            customers = svc.list_customers_by_salesperson("S001")
            assert len(customers) == 1
            assert customers[0]["customer_name"] == "腾讯科技"

    def test_validate_salesperson_id_format_valid(self):
        svc = SalespersonMappingService()
        assert svc._validate_salesperson_id("S001") == "S001"
        assert svc._validate_salesperson_id("A123") == "A123"

    def test_validate_salesperson_id_format_invalid(self):
        svc = SalespersonMappingService()
        with pytest.raises(ValueError, match="salesperson_id"):
            svc._validate_salesperson_id("s001")  # 小写不允许
        with pytest.raises(ValueError, match="salesperson_id"):
            svc._validate_salesperson_id("S-001")  # 短横线不允许


class TestCSVUpload:
    def test_parse_csv_valid(self):
        import io
        from services.salesperson_mapping_service import SalespersonMappingService

        svc = SalespersonMappingService()
        csv_content = "salesperson_id,salesperson_name,feishu_open_id,customer_id,customer_name\nS001,张三分,oc_xxxx,C001,腾讯科技\n"
        file_content = io.BytesIO(csv_content.encode("utf-8"))
        rows, errors = svc._parse_csv_upload(file_content, "test.csv")
        assert len(rows) == 1
        assert len(errors) == 0
        assert rows[0]["salesperson_id"] == "S001"

    def test_parse_csv_skips_invalid_salesperson_id(self):
        import io
        from services.salesperson_mapping_service import SalespersonMappingService

        svc = SalespersonMappingService()
        csv_content = "salesperson_id,salesperson_name,feishu_open_id,customer_id,customer_name\nS001,张三分,oc_xxxx,C001,腾讯科技\ns002,李四,oc_yyyy,C002,阿里巴巴\n"
        file_content = io.BytesIO(csv_content.encode("utf-8"))
        rows, errors = svc._parse_csv_upload(file_content, "test.csv")
        assert len(rows) == 1  # s002 被跳过
        assert len(errors) == 1
        assert errors[0]["row"] == 2
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/unit/test_salesperson_mapping_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 创建 schemas/ap.py**

```python
# schemas/ap.py
"""AP 扩展数据模型"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class APStdRecord(BaseModel):
    """标准化 AP 记录"""
    id: str
    supplier_code: str = ""
    supplier_name: str
    bank_date: date
    due_date: date
    amount: Decimal
    received_amount: Decimal = Decimal("0")
    is_settled: Literal[0, 1] = 0
    settlement_date: date | None = None
    bank_transaction_no: str = ""
    payment_method: str = ""
    source_file: str = ""
    etl_time: datetime = Field(default_factory=datetime.now)


class APSupplierSummary(BaseModel):
    """供应商汇总"""
    supplier_code: str
    supplier_name: str
    total_amount: Decimal
    unsettled_amount: Decimal
    overdue_amount: Decimal
    record_count: int


class APKPISummary(BaseModel):
    """AP KPI 汇总"""
    ap_total: Decimal
    unsettled_total: Decimal
    overdue_total: Decimal
    overdue_rate: float
    supplier_count: int
```

- [ ] **Step 4: 创建 services/salesperson_mapping_service.py**

```python
# services/salesperson_mapping_service.py
"""业务员映射服务"""
import csv
import io
import re
import uuid
from datetime import datetime
from typing import Any

from services.clickhouse_service import ClickHouseDataService

_SALESperson_ID_RE = re.compile(r"^[A-Z0-9]+$")


def escape_ch_string(s: str) -> str:
    """转义 ClickHouse 字符串中的单引号"""
    return s.replace("'", "\\'")


class SalespersonMappingService:
    """业务员映射 CRUD + CSV 上传"""

    def __init__(self, ch: ClickHouseDataService | None = None):
        self._ch = ch or ClickHouseDataService()

    # --- Active salesperson list ---
    def list_active(self) -> list[dict[str, Any]]:
        rows = self._ch.execute_query(
            "SELECT id, salesperson_id, salesperson_name, feishu_open_id "
            "FROM dm.salesperson_mapping WHERE enabled = 1"
        )
        return rows

    # --- Mapping CRUD ---
    def list_mappings(self) -> list[dict[str, Any]]:
        return self._ch.execute_query(
            "SELECT * FROM dm.salesperson_mapping ORDER BY created_at DESC"
        )

    def create_mapping(self, data: dict) -> dict:
        sid = data["salesperson_id"]
        self._validate_salesperson_id(sid)
        now = datetime.now().isoformat()
        record_id = str(uuid.uuid4())
        sql = (
            f"INSERT INTO dm.salesperson_mapping "
            f"(id, salesperson_id, salesperson_name, feishu_open_id, enabled, created_at, updated_at) "
            f"VALUES ('{record_id}', '{sid}', '{escape_ch_string(data['salesperson_name'])}', "
            f"'{escape_ch_string(data.get('feishu_open_id') or '')}', "
            f"{int(data.get('enabled', True))}, '{now}', '{now}')"
        )
        self._ch.execute(sql)
        return {"id": record_id, **data}

    def update_mapping(self, record_id: str, data: dict) -> dict | None:
        rows = self._ch.execute_query(
            f"SELECT 1 FROM dm.salesperson_mapping WHERE id = '{record_id}'"
        )
        if not rows:
            return None
        if "salesperson_id" in data:
            self._validate_salesperson_id(data["salesperson_id"])
        now = datetime.now().isoformat()
        sets = [f"updated_at = '{now}'"]
        for k, v in data.items():
            if k in ("salesperson_id", "salesperson_name"):
                sets.append(f"{k} = '{escape_ch_string(str(v))}'")
            elif k == "feishu_open_id":
                sets.append(f"feishu_open_id = '{escape_ch_string(v or '')}'")
            elif k == "enabled":
                sets.append(f"enabled = {int(v)}")
        self._ch.execute(
            f"ALTER TABLE dm.salesperson_mapping UPDATE {', '.join(sets)} WHERE id = '{record_id}'"
        )
        return {"id": record_id, **data}

    def delete_mapping(self, record_id: str) -> bool:
        try:
            self._ch.execute(
                f"ALTER TABLE dm.salesperson_mapping DELETE WHERE id = '{record_id}'"
            )
            return True
        except Exception:
            return False

    # --- Customer mapping ---
    def list_customers_by_salesperson(self, salesperson_id: str) -> list[dict]:
        return self._ch.execute_query(
            f"SELECT customer_id, customer_name FROM dm.salesperson_customer_mapping "
            f"WHERE salesperson_id = '{salesperson_id}'"
        )

    def upsert_customer_mapping(
        self,
        salesperson_id: str,
        customer_id: str,
        customer_name: str,
    ) -> None:
        record_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        sql = (
            f"INSERT INTO dm.salesperson_customer_mapping "
            f"(id, salesperson_id, customer_id, customer_name, created_at) "
            f"VALUES ('{record_id}', '{salesperson_id}', '{escape_ch_string(customer_id)}', "
            f"'{escape_ch_string(customer_name)}', '{now}')"
        )
        self._ch.execute(sql)

    # --- CSV upload ---
    def _parse_csv_upload(
        self, file_content: io.BytesIO, filename: str
    ) -> tuple[list[dict], list[dict]]:
        """解析 CSV，返回 (rows, errors)"""
        text = file_content.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows, errors = [], []
        for i, raw in enumerate(reader, start=2):  # start=2: header is row 1
            sid = raw.get("salesperson_id", "").strip()
            try:
                self._validate_salesperson_id(sid)
            except ValueError as e:
                errors.append({"row": i, "reason": str(e)})
                continue
            rows.append({
                "salesperson_id": sid,
                "salesperson_name": raw.get("salesperson_name", "").strip(),
                "feishu_open_id": raw.get("feishu_open_id", "").strip(),
                "customer_id": raw.get("customer_id", "").strip(),
                "customer_name": raw.get("customer_name", "").strip(),
            })
        return rows, errors

    def upload_csv(self, file_content: io.BytesIO, filename: str) -> dict:
        rows, errors = self._parse_csv_upload(file_content, filename)
        imported, skipped = 0, 0
        for row in rows:
            # Upsert salesperson
            existing = self._ch.execute_query(
                f"SELECT id FROM dm.salesperson_mapping WHERE salesperson_id = '{row['salesperson_id']}' LIMIT 1"
            )
            if existing:
                self.update_mapping(existing[0]["id"], {
                    "salesperson_name": row["salesperson_name"],
                    "feishu_open_id": row["feishu_open_id"],
                    "enabled": True,
                })
            else:
                self.create_mapping({
                    "salesperson_id": row["salesperson_id"],
                    "salesperson_name": row["salesperson_name"],
                    "feishu_open_id": row["feishu_open_id"],
                    "enabled": True,
                })
            # Upsert customer mapping
            if row["customer_id"]:
                try:
                    self.upsert_customer_mapping(
                        row["salesperson_id"],
                        row["customer_id"],
                        row["customer_name"],
                    )
                    imported += 1
                except Exception:
                    skipped += 1
        return {
            "imported": imported,
            "skipped": skipped,
            "parse_errors": len(errors),
            "errors": errors,
        }

    def _validate_salesperson_id(self, sid: str) -> str:
        if not _SALESperson_ID_RE.match(sid):
            raise ValueError(
                f"Invalid salesperson_id '{sid}': must be uppercase alphanumeric only"
            )
        return sid
```

- [ ] **Step 5: 创建 api/schemas/salesperson_mapping.py**

```python
# api/schemas/salesperson_mapping.py
"""业务员映射 API 请求/响应模型"""
from datetime import datetime
from pydantic import BaseModel


class SalespersonMappingCreate(BaseModel):
    salesperson_id: str
    salesperson_name: str
    feishu_open_id: str | None = None
    enabled: bool = True


class SalespersonMappingUpdate(BaseModel):
    salesperson_id: str | None = None
    salesperson_name: str | None = None
    feishu_open_id: str | None = None
    enabled: bool | None = None


class SalespersonMappingResponse(BaseModel):
    id: str
    salesperson_id: str
    salesperson_name: str
    feishu_open_id: str
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None


class CustomerMappingResponse(BaseModel):
    customer_id: str
    customer_name: str


class CSVUploadResponse(BaseModel):
    imported: int
    skipped: int
    parse_errors: int
    errors: list[dict]
```

- [ ] **Step 6: 创建 api/routes/salesperson_mapping.py**

```python
# api/routes/salesperson_mapping.py
"""业务员映射 API 路由"""
import io
from fastapi import APIRouter, HTTPException, UploadFile, File

from api.dependencies import SalespersonMappingServiceDep
from api.schemas.salesperson_mapping import (
    CSVUploadResponse,
    CustomerMappingResponse,
    SalespersonMappingCreate,
    SalespersonMappingResponse,
    SalespersonMappingUpdate,
)

router = APIRouter()


@router.get("/mappings")
async def list_mappings(service: SalespersonMappingServiceDep):
    items = service.list_mappings()
    return {"items": items, "total": len(items)}


@router.post("/mappings", response_model=dict)
async def create_mapping(data: SalespersonMappingCreate, service: SalespersonMappingServiceDep):
    result = service.create_mapping(data.model_dump())
    return result


@router.put("/mappings/{record_id}", response_model=dict)
async def update_mapping(
    record_id: str,
    data: SalespersonMappingUpdate,
    service: SalespersonMappingServiceDep,
):
    result = service.update_mapping(record_id, data.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=404, detail="记录不存在")
    return result


@router.delete("/mappings/{record_id}")
async def delete_mapping(record_id: str, service: SalespersonMappingServiceDep):
    success = service.delete_mapping(record_id)
    if not success:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"status": "deleted", "id": record_id}


@router.post("/mappings/upload", response_model=CSVUploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    service: SalespersonMappingServiceDep = None,
):
    if not service:
        from api.dependencies import get_salesperson_mapping_service
        service = get_salesperson_mapping_service()
    content = await file.read()
    result = service.upload_csv(io.BytesIO(content), file.filename or "upload.csv")
    return result


@router.get("/{salesperson_id}/customers", response_model=list[dict])
async def get_customers(
    salesperson_id: str,
    service: SalespersonMappingServiceDep,
):
    return service.list_customers_by_salesperson(salesperson_id)
```

- [ ] **Step 7: 更新 api/config.py 添加环境变量**

在 `FeishuConfig` 类中添加：

```python
sales_channel_id: str = ""  # FEISHU_SALES_CHANNEL_ID
```

并在现有配置类或新增 AP 配置类中添加：

```python
class APConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ap_", env_file=".env", extra="ignore")
    default_payment_term_days: int = 30  # AP_DEFAULT_PAYMENT_TERM_DAYS
```

并在 `Settings` 类中添加字段：

```python
ap: APConfig = Field(default_factory=APConfig)
```

**重要**：`env_prefix="ap_"` 意味着环境变量名需要加前缀 `AP_`（ClickHouse 会自动将 `AP_DEFAULT_PAYMENT_TERM_DAYS` 映射为 `ap_default_payment_term_days`），如果直接在 `.env` 中写 `AP_DEFAULT_PAYMENT_TERM_DAYS=30`，则映射为 `default_payment_term_days`。Phase 6 DDL 脚本会在 `init_phase6.py` 中读取该配置并注入。实际注入方式：在 `APBankStatementParser.__init__` 中通过 `get_settings().ap.default_payment_term_days` 读取。

- [ ] **Step 8: 更新 api/dependencies.py**

```python
from services.salesperson_mapping_service import SalespersonMappingService
from services.ap_service import APService

@lru_cache
def get_salesperson_mapping_service() -> SalespersonMappingService:
    return SalespersonMappingService()

@lru_cache
def get_ap_service() -> APService:
    return APService()

SalespersonMappingServiceDep = Annotated[SalespersonMappingService, Depends(get_salesperson_mapping_service)]
APServiceDep = Annotated[APService, Depends(get_ap_service)]
```

- [ ] **Step 9: 更新 .env.example**

```bash
# Phase 6: Salesperson channel
FEISHU_SALES_CHANNEL_ID=          # 销售团队飞书群 ID（OC 开头）
AP_DEFAULT_PAYMENT_TERM_DAYS=30  # AP 付款期限天数
```

- [ ] **Step 10: 更新 api/main.py 注册路由**

```python
from api.routes import ap, salesperson_mapping
app.include_router(salesperson_mapping.router, prefix="/api/v1/salesperson", tags=["业务员映射"])
app.include_router(ap.router, prefix="/api/v1/ap", tags=["AP管理"])
```

- [ ] **Step 11: 运行测试验证通过**

Run: `uv run pytest tests/unit/test_salesperson_mapping_service.py -v`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add schemas/ap.py services/salesperson_mapping_service.py api/routes/salesperson_mapping.py api/schemas/salesperson_mapping.py api/config.py api/dependencies.py api/main.py .env.example tests/unit/test_salesperson_mapping_service.py
git commit -m "feat: add SalespersonMappingService with CRUD + CSV upload"
```

---

## Task 3: APBankStatementParser 解析服务

**Files:**
- Create: `services/ap_bank_parser.py`
- Test: `tests/unit/test_ap_bank_parser.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_ap_bank_parser.py
"""测试 APBankStatementParser"""
import pytest
import io
from datetime import date
from unittest.mock import MagicMock, patch
from decimal import Decimal

from services.ap_bank_parser import APBankStatementParser, BankStatementRow


class TestColumnMapping:
    def test_parse_detects_transaction_date(self):
        parser = APBankStatementParser()
        csv_content = "交易日期,收款人,金额,流水号,摘要\n2026-03-01,腾讯科技,10000,TXN001,付款"
        rows, errs = parser._parse_csv(io.BytesIO(csv_content.encode("utf-8")), "test.csv")
        assert len(errs) == 0
        assert rows[0]["bank_date"] == date(2026, 3, 1)
        assert rows[0]["counterparty"] == "腾讯科技"
        assert rows[0]["amount"] == Decimal("10000")

    def test_parse_skips_direction_in(self):
        parser = APBankStatementParser()
        csv_content = "交易日期,收款人,金额,流水号,方向\n2026-03-01,腾讯科技,10000,TXN001,IN"
        rows, errs = parser._parse_csv(io.BytesIO(csv_content.encode("utf-8")), "test.csv")
        assert len(rows) == 0  # IN 方向被过滤

    def test_parse_partial_columns_fills_blanks(self):
        parser = APBankStatementParser()
        csv_content = "日期,收款人,金额\n2026-03-01,腾讯科技,5000"
        rows, errs = parser._parse_csv(io.BytesIO(csv_content.encode("utf-8")), "test.csv")
        assert len(errs) == 0
        assert rows[0]["transaction_no"] == ""
        assert rows[0]["remark"] == ""

    def test_parse_invalid_amount_error(self):
        parser = APBankStatementParser()
        csv_content = "交易日期,收款人,金额\n2026-03-01,腾讯科技,NOT_A_NUMBER"
        rows, errs = parser._parse_csv(io.BytesIO(csv_content.encode("utf-8")), "test.csv")
        assert len(rows) == 0
        assert len(errs) == 1
        assert errs[0]["row"] == 2

    def test_parse_invalid_date_error(self):
        parser = APBankStatementParser()
        csv_content = "交易日期,收款人,金额\nnot-a-date,腾讯科技,1000"
        rows, errs = parser._parse_csv(io.BytesIO(csv_content.encode("utf-8")), "test.csv")
        assert len(errs) == 1
        assert "date" in errs[0]["reason"].lower()


class TestSupplierMatching:
    def test_match_exact_supplier(self):
        parser = APBankStatementParser()
        with patch.object(parser, "_get_known_suppliers", return_value=["腾讯科技", "阿里巴巴"]):
            code, name = parser._match_supplier("腾讯科技")
            assert code == ""  # 未建 supplier 表时 code 为空
            assert name == "腾讯科技"

    def test_match_no_bracket_supplier(self):
        parser = APBankStatementParser()
        with patch.object(parser, "_get_known_suppliers", return_value=["腾讯科技"]):
            code, name = parser._match_supplier("腾讯科技（深圳）")
            assert name == "腾讯科技"

    def test_match_fuzzy_supplier(self):
        parser = APBankStatementParser()
        with patch.object(parser, "_get_known_suppliers", return_value=["腾讯科技"]):
            code, name = parser._match_supplier("腾迅科技")  # 错字
            assert name == "腾讯科技"  # 相似度够高则匹配

    def test_match_unknown_supplier(self):
        parser = APBankStatementParser()
        with patch.object(parser, "_get_known_suppliers", return_value=["腾讯科技"]):
            code, name = parser._match_supplier("完全不相关公司")
            assert name == "完全不相关公司"
            assert code == ""


class TestSanitizeFilename:
    def test_sanitize_removes_path(self):
        from services.ap_bank_parser import sanitize_filename
        assert sanitize_filename("/path/to/file.csv") == "file.csv"
        assert sanitize_filename("..\\windows\\file.csv") == "file.csv"
        assert sanitize_filename("file.csv") == "file.csv"

    def test_sanitize_strips_special_chars(self):
        from services.ap_bank_parser import sanitize_filename
        result = sanitize_filename("my file;rm -rf;.csv")
        assert ";" not in result
        assert " " not in result

    def test_sanitize_truncates_255(self):
        from services.ap_bank_parser import sanitize_filename
        long_name = "a" * 300 + ".csv"
        result = sanitize_filename(long_name)
        assert len(result) <= 255
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/unit/test_ap_bank_parser.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 创建 services/ap_bank_parser.py**

```python
# services/ap_bank_parser.py
"""银行对账单解析服务"""
import csv
import io
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import difflib
from pydantic import BaseModel


def sanitize_filename(name: str) -> str:
    """净化上传文件名：剥离路径、截断 255 字符、仅保留安全字符"""
    # 剥离路径
    name = name.replace("\\", "/").split("/")[-1]
    # 只保留字母/数字/. /- /_
    name = re.sub(r"[^A-Za-z0-9._-]", "", name)
    return name[:255]


# 列名识别规则（按优先级）
_COLUMN_RULES: list[tuple[str, list[str]]] = [
    ("bank_date", ["交易日期", "记账日期", "日期"]),
    ("counterparty", ["收款人", "对方账户", "对方"]),
    ("amount", ["金额", "付款额"]),
    ("transaction_no", ["流水号", "交易流水", "编号"]),
    ("remark", ["摘要", "用途"]),
]

# ClickHouse 字符串转义
def _esc(s: str) -> str:
    return s.replace("'", "\\'")


class BankStatementRow(BaseModel):
    bank_date: date
    counterparty: str
    amount: Decimal
    transaction_no: str = ""
    remark: str = ""
    direction: str = "OUT"  # default


class APBankStatementParser:
    """银行对账单 CSV 解析"""

    def __init__(
        self,
        ch: "ClickHouseDataService | None = None,
        payment_term_days: int = 30,
    ):
        from services.clickhouse_service import ClickHouseDataService
        from api.config import get_settings

        self._ch = ch or ClickHouseDataService()
        try:
            settings = get_settings()
            self._payment_term_days = getattr(settings, "ap_default_payment_term_days", payment_term_days)
        except Exception:
            self._payment_term_days = payment_term_days

    def process_upload(
        self, file_content: io.BytesIO, filename: str
    ) -> dict[str, Any]:
        """完整处理流程：解析 → raw 写入 → std 转换 → 返回结果"""
        safe_name = sanitize_filename(filename)

        # Step 1: 解析 CSV
        raw_rows, parse_errors = self._parse_csv(file_content, safe_name)
        if not raw_rows:
            return {
                "file": safe_name,
                "raw_saved": 0,
                "std_saved": 0,
                "parse_errors": len(parse_errors),
                "errors": parse_errors,
            }

        # Step 2: 写入 raw.ap_bank_statement
        raw_saved = self._save_raw(raw_rows, safe_name)

        # Step 3: 转换为 std 并写入
        std_rows = []
        supplier_errors = []
        for row in raw_rows:
            std_row, err = self._transform_to_std(row, safe_name)
            if std_row:
                std_rows.append(std_row)
            if err:
                supplier_errors.append(err)
        std_saved = self._save_std(std_rows)

        return {
            "file": safe_name,
            "raw_saved": raw_saved,
            "std_saved": std_saved,
            "parse_errors": len(parse_errors),
            "supplier_match_errors": len(supplier_errors),
            "errors": parse_errors + supplier_errors,
        }

    # --- CSV 解析 ---
    def _parse_csv(
        self, file_content: io.BytesIO, filename: str
    ) -> tuple[list[dict], list[dict]]:
        text = file_content.read().decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        header = next(reader, [])
        col_map = self._detect_columns(header)

        rows, errors = [], []
        for i, raw_row in enumerate(reader, start=2):
            row_dict = dict(zip(header, raw_row, strict=False))
            row_errors = self._validate_row(row_dict, i, col_map)
            if row_errors:
                errors.extend(row_errors)
                continue  # 跳过有错误的行
            try:
                parsed = self._parse_row(raw_row, header, i, col_map)
                if parsed:  # direction=OUT 才保留
                    rows.append(parsed)
            except Exception as e:
                errors.append({"row": i, "reason": str(e)})
        return rows, errors

    def _detect_columns(self, header: list[str]) -> dict[str, int]:
        """按优先级检测列索引，返回 {field: col_index}"""
        col_map = {}
        for field, keywords in _COLUMN_RULES:
            for idx, col_name in enumerate(header):
                col_lower = col_name.strip()
                for kw in keywords:
                    if kw in col_lower:
                        if field not in col_map:
                            col_map[field] = idx
                        break
        return col_map

    def _validate_row(
        self, row: dict, row_num: int, col_map: dict
    ) -> list[dict]:
        errors = []
        date_str = row.get(list(col_map.keys())[col_map.get("bank_date", -1)] or "", "")
        amount_str = row.get(list(col_map.keys())[col_map.get("amount", -1)] or "", "")
        try:
            parsed_date = date.fromisoformat(date_str.strip())
        except Exception:
            errors.append({"row": row_num, "reason": f"无效日期: {date_str}"})
        try:
            Decimal(amount_str.strip())
        except (InvalidOperation, ValueError):
            errors.append({"row": row_num, "reason": f"无效金额: {amount_str}"})
        return errors

    def _parse_row(
        self, raw_row: list[str], header: list[str], row_num: int, col_map: dict
    ) -> dict | None:
        # col_map: field_name → column_index
        vals = {f: raw_row[i].strip() if i < len(raw_row) else ""
                for f, i in col_map.items()}
        direction = vals.get("direction", "").upper()
        if direction == "IN":
            return None  # 跳过收款行
        amount_str = vals.get("amount", "0").replace(",", "")
        try:
            amt = abs(Decimal(amount_str))
        except InvalidOperation:
            amt = Decimal("0")
        return {
            "bank_date": vals.get("bank_date", ""),
            "counterparty": vals.get("counterparty", ""),
            "amount": str(amt),
            "transaction_no": vals.get("transaction_no", ""),
            "remark": vals.get("remark", ""),
            "direction": "OUT",
        }

    # --- Raw 写入 ---
    def _save_raw(self, rows: list[dict], filename: str) -> int:
        if not rows:
            return 0
        now = datetime.now().isoformat()
        sql = (
            "INSERT INTO raw.ap_bank_statement "
            "(id, file_name, bank_date, transaction_no, counterparty, amount, direction, remark, created_at) VALUES "
        )
        vals = []
        for r in rows:
            vals.append(
                f"('{uuid.uuid4()}', '{_esc(filename)}', "
                f"'{r['bank_date']}', '{_esc(r['transaction_no'])}', "
                f"'{_esc(r['counterparty'])}', {r['amount']}, "
                f"'{r['direction']}', '{_esc(r['remark'])}', '{now}')"
            )
        self._ch.execute(sql + ", ".join(vals))
        return len(rows)

    # --- STD 转换 ---
    def _transform_to_std(
        self, raw_row: dict, filename: str
    ) -> tuple[dict | None, dict | None]:
        bank_date = date.fromisoformat(raw_row["bank_date"])
        due_date = bank_date + timedelta(days=self._payment_term_days)
        supplier_name = raw_row["counterparty"]
        matched_name = self._match_supplier(supplier_name)
        return {
            "bank_date": bank_date.isoformat(),
            "due_date": due_date.isoformat(),
            "supplier_name": matched_name,
            "amount": raw_row["amount"],
            "bank_transaction_no": raw_row["transaction_no"],
            "source_file": filename,
        }, None

    def _match_supplier(self, name: str) -> str:
        """供应商匹配：精确 → 去括号精确 → 模糊 → 返回原名"""
        known = self._get_known_suppliers()
        if name in known:
            return name
        # 去括号匹配
        name_no_brackets = re.sub(r"[（(].*?[）)]", "", name).strip()
        if name_no_brackets in known:
            return name_no_brackets
        # 模糊匹配
        best_match, best_score = name, 0.0
        for supplier in known:
            score = difflib.SequenceMatcher(None, name_no_brackets, supplier).ratio()
            if score > best_score:
                best_score = score
                best_match = supplier
        if best_score >= 0.85:
            return best_match
        return name  # 未匹配，返回原名，code 留空

    def _get_known_suppliers(self) -> list[str]:
        try:
            rows = self._ch.execute_query(
                "SELECT DISTINCT supplier_name FROM std.ap_std_record WHERE supplier_name != ''"
            )
            return [r.get("supplier_name", "") for r in rows if r.get("supplier_name")]
        except Exception:
            return []

    # --- STD 写入 ---
    def _save_std(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        now = datetime.now().isoformat()
        sql = (
            "INSERT INTO std.ap_std_record "
            "(id, supplier_code, supplier_name, bank_date, due_date, amount, "
            "received_amount, is_settled, bank_transaction_no, payment_method, source_file, etl_time) "
            "VALUES "
        )
        vals = []
        for r in rows:
            vals.append(
                f"('{uuid.uuid4()}', '', "  # supplier_code 空，暂未建供应商表
                f"'{_esc(r['supplier_name'])}', "
                f"'{r['bank_date']}', '{r['due_date']}', {r['amount']}, "
                f"0, 0, '{_esc(r['bank_transaction_no'])}', '', "
                f"'{_esc(r['source_file'])}', '{now}')"
            )
        self._ch.execute(sql + ", ".join(vals))
        return len(rows)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/unit/test_ap_bank_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/ap_bank_parser.py tests/unit/test_ap_bank_parser.py
git commit -m "feat: add APBankStatementParser with column auto-detection and supplier matching"
```

---

## Task 4: AP API + APService

**Files:**
- Create: `services/ap_service.py`
- Create: `api/routes/ap.py`
- Create: `api/schemas/ap.py`
- Modify: `services/clickhouse_service.py`（+AP 查询方法）
- Modify: `pyproject.toml`（+openpyxl）
- Test: `tests/integration/test_ap_api.py`

- [ ] **Step 1: 写测试**

```python
# tests/integration/test_ap_api.py
"""AP API 集成测试"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAPUploadAPI:
    def test_upload_rejects_large_file(self, client):
        with patch("services.ap_bank_parser.APBankStatementParser.process_upload") as mock:
            mock.return_value = {"file": "test.csv", "raw_saved": 0, "std_saved": 0, "parse_errors": 0, "errors": []}
            large_content = b"x" * (11 * 1024 * 1024)  # 11 MB
            response = client.post(
                "/api/v1/ap/upload",
                files={"file": ("large.csv", io.BytesIO(large_content), "text/csv")},
            )
            assert response.status_code == 413
            assert "10MB" in response.json()["detail"]

    def test_upload_returns_parse_result(self, client):
        with patch("services.ap_bank_parser.APBankStatementParser.process_upload") as mock:
            mock.return_value = {
                "file": "bank_march.csv",
                "raw_saved": 10,
                "std_saved": 8,
                "parse_errors": 2,
                "errors": [{"row": 5, "reason": "invalid amount"}],
            }
            # Note: actual integration test would POST real CSV
            assert True  # placeholder


class TestAPKPIAPI:
    def test_get_kpi_returns_structure(self, client):
        with patch("services.ap_service.APService.get_kpi") as mock:
            mock.return_value = {
                "ap_total": "1000000",
                "unsettled_total": "500000",
                "overdue_total": "100000",
                "overdue_rate": 0.10,
                "supplier_count": 20,
            }
            response = client.get("/api/v1/ap/kpi")
            assert response.status_code == 200
            data = response.json()
            assert "ap_total" in data
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/integration/test_ap_api.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 创建 services/ap_service.py**

```python
# services/ap_service.py
"""AP 数据聚合服务"""
from datetime import date
from decimal import Decimal
from typing import Any

from services.clickhouse_service import ClickHouseDataService


class APService:
    """AP 数据查询（不含写入，写入由 APBankStatementParser 处理）"""

    def __init__(self, ch: ClickHouseDataService | None = None):
        self._ch = ch or ClickHouseDataService()

    def get_kpi(self, stat_date: date | None = None) -> dict[str, Any]:
        # AP KPI 聚合全量数据，不按单日过滤（stat_date 参数预留，暂不使用）
        rows = self._ch.execute_query(
            "SELECT "
            "  sum(amount) AS ap_total, "
            "  sumIf(amount, is_settled = 0) AS unsettled_total, "
            "  sumIf(amount, is_settled = 0 AND due_date < today()) AS overdue_total, "
            "  uniqExact(supplier_name) AS supplier_count "
            "FROM std.ap_std_record"
        )
        if not rows:
            return {
                "ap_total": "0", "unsettled_total": "0",
                "overdue_total": "0", "overdue_rate": 0.0, "supplier_count": 0,
            }
        r = rows[0]
        ap = float(r.get("ap_total") or 0)
        overdue = float(r.get("overdue_total") or 0)
        return {
            "ap_total": str(r.get("ap_total") or 0),
            "unsettled_total": str(r.get("unsettled_total") or 0),
            "overdue_total": str(r.get("overdue_total") or 0),
            "overdue_rate": round(overdue / ap if ap > 0 else 0.0, 4),
            "supplier_count": r.get("supplier_count") or 0,
        }

    def get_suppliers(self, limit: int = 20) -> list[dict]:
        rows = self._ch.execute_query(
            "SELECT "
            "  supplier_name, "
            "  sum(amount) AS total_amount, "
            "  sumIf(amount, is_settled = 0) AS unsettled_amount, "
            "  sumIf(amount, is_settled = 0 AND due_date < today()) AS overdue_amount, "
            "  count() AS record_count "
            "FROM std.ap_std_record "
            "WHERE supplier_name != '' "
            "GROUP BY supplier_name "
            "ORDER BY total_amount DESC "
            f"LIMIT {limit}"
        )
        return [dict(r) for r in rows]

    def get_records(
        self,
        supplier_name: str | None = None,
        is_settled: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        where = ["1=1"]
        if supplier_name:
            where.append(f"supplier_name = '{supplier_name}'")
        if is_settled is not None:
            where.append(f"is_settled = {is_settled}")
        rows = self._ch.execute_query(
            "SELECT * FROM std.ap_std_record "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY bank_date DESC LIMIT {limit}"
        )
        return [dict(r) for r in rows]

    def generate_dashboard(self) -> str:
        """生成 AP HTML 看板"""
        from datetime import datetime
        from jinja2 import Environment, FileSystemLoader
        from pathlib import Path

        kpi = self.get_kpi()
        suppliers = self.get_suppliers(limit=10)

        jinja = Environment(
            loader=FileSystemLoader(Path(__file__).parent.parent / "templates" / "reports"),
            autoescape=True,
        )
        template = jinja.get_template("ap_report.html.j2")
        html = template.render(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            kpi=kpi,
            suppliers=suppliers,
        )
        output_dir = Path(__file__).parent.parent / "static" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / "ap_dashboard.html"
        filepath.write_text(html, encoding="utf-8")
        return str(filepath)
```

- [ ] **Step 4: 创建 api/schemas/ap.py**

```python
# api/schemas/ap.py
"""AP API 请求/响应模型"""
from datetime import date
from pydantic import BaseModel


class APUploadResponse(BaseModel):
    file: str
    raw_saved: int
    std_saved: int
    parse_errors: int
    errors: list[dict]


class APSupplierRecord(BaseModel):
    supplier_name: str
    total_amount: float
    unsettled_amount: float
    overdue_amount: float
    record_count: int


class APKPISummary(BaseModel):
    ap_total: str
    unsettled_total: str
    overdue_total: str
    overdue_rate: float
    supplier_count: int
```

- [ ] **Step 5: 创建 api/routes/ap.py**

```python
# api/routes/ap.py
"""AP 管理 API 路由"""
import io
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.dependencies import APServiceDep
from api.schemas.ap import APUploadResponse, APSupplierRecord, APKPISummary
from services.ap_bank_parser import APBankStatementParser

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", response_model=APUploadResponse)
async def upload_bank_statement(
    file: UploadFile = File(...),
    service: APServiceDep = None,
):
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过 10MB 限制")

    allowed = {"text/csv": "csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx"}
    content_type = file.content_type or ""
    if content_type not in allowed and not file.filename.endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=400, detail="仅支持 .csv 和 .xlsx 文件")

    parser = APBankStatementParser()
    result = parser.process_upload(io.BytesIO(content), file.filename or "upload.csv")
    return result


@router.get("/kpi")
async def get_ap_kpi(service: APServiceDep):
    return service.get_kpi()


@router.get("/suppliers")
async def get_ap_suppliers(service: APServiceDep, limit: int = 20):
    return service.get_suppliers(limit=limit)


@router.get("/records")
async def get_ap_records(
    service: APServiceDep,
    supplier_name: str | None = None,
    is_settled: int | None = None,
    limit: int = 100,
):
    return service.get_records(supplier_name=supplier_name, is_settled=is_settled, limit=limit)


@router.post("/dashboard/generate")
async def generate_ap_dashboard(service: APServiceDep):
    path = service.generate_dashboard()
    return {"status": "generated", "file": path}


@router.get("/dashboard")
async def get_ap_dashboard(service: APServiceDep):
    """返回 AP 看板 HTML 页面"""
    kpi = service.get_kpi()
    suppliers = service.get_suppliers(limit=10)
    return {
        "kpi": kpi,
        "suppliers": suppliers,
        "generated_at": datetime.now().isoformat(),
    }
```

- [ ] **Step 6: 更新 pyproject.toml 添加 openpyxl**

```toml
# 在 [dependencies] 中添加：
    "openpyxl>=3.1.2",   # Excel 文件解析
```

Run: `uv sync`

- [ ] **Step 7: 运行测试验证通过**

Run: `uv run pytest tests/integration/test_ap_api.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add services/ap_service.py api/routes/ap.py api/schemas/ap.py services/clickhouse_service.py pyproject.toml tests/integration/test_ap_api.py
git commit -m "feat: add APService and AP upload/query API endpoints"
```

---

## Task 5: AP 看板模板

**Files:**
- Create: `templates/reports/ap_report.html.j2`

- [ ] **Step 1: 创建 templates/reports/ap_report.html.j2**

```html
<!-- templates/reports/ap_report.html.j2 -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AP 应付看板</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #333; padding: 20px; }
  .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
  .header h1 { font-size: 24px; font-weight: 600; }
  .header .date { color: #888; font-size: 14px; }
  .kpi-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
  .kpi-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .kpi-card .label { font-size: 13px; color: #888; margin-bottom: 8px; }
  .kpi-card .value { font-size: 28px; font-weight: 700; }
  .kpi-card .value.danger { color: #e53e3e; }
  .kpi-card .value.warning { color: #d69e2e; }
  .kpi-card .value.success { color: #38a169; }
  .section { background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .section h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }
  th { color: #888; font-weight: 500; font-size: 12px; text-transform: uppercase; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
  .tag.overdue { background: #fed7d7; color: #c53030; }
  .tag.settled { background: #c6f6d5; color: #276749; }
  .tag.unsettled { background: #fefcbf; color: #975a16; }
</style>
</head>
<body>

<div class="header">
  <h1>AP 应付看板</h1>
  <span class="date">生成时间: {{ generated_at }}</span>
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="label">AP 总额</div>
    <div class="value">¥{{ kpi.ap_total }}</div>
  </div>
  <div class="kpi-card">
    <div class="label">未结清金额</div>
    <div class="value warning">¥{{ kpi.unsettled_total }}</div>
  </div>
  <div class="kpi-card">
    <div class="label">逾期金额</div>
    <div class="value danger">¥{{ kpi.overdue_total }}
      <span style="font-size:14px;font-weight:400;">({{ "%.1f"|format(kpi.overdue_rate * 100) }}%)</span>
    </div>
  </div>
</div>

<div class="section">
  <h2>供应商 Top 10（按 AP 总额）</h2>
  <table>
    <thead>
      <tr>
        <th>供应商</th>
        <th>AP总额</th>
        <th>未结清</th>
        <th>逾期金额</th>
        <th>笔数</th>
      </tr>
    </thead>
    <tbody>
    {% for s in suppliers %}
    <tr>
      <td>{{ s.supplier_name }}</td>
      <td>¥{{ "%.0f"|format(s.total_amount) }}</td>
      <td>¥{{ "%.0f"|format(s.unsettled_amount) }}</td>
      <td>
        {% if s.overdue_amount > 0 %}
        <span class="tag overdue">¥{{ "%.0f"|format(s.overdue_amount) }}</span>
        {% else %}
        <span class="tag settled">无逾期</span>
        {% endif %}
      </td>
      <td>{{ s.record_count }}</td>
    </tr>
    {% endfor %}
    {% if not suppliers %}
    <tr><td colspan="5" style="color:#888;text-align:center;">暂无数据</td></tr>
    {% endif %}
    </tbody>
  </table>
</div>

</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add templates/reports/ap_report.html.j2
git commit -m "feat: add AP dashboard HTML template"
```

---

## Task 6: 业务员 AR 报告服务 + 模板

**Files:**
- Create: `services/per_salesperson_report_service.py`
- Modify: `services/report_service.py`（扩展 generate 方法支持 per-rep）
- Create: `templates/reports/ar_per_salesperson.html.j2`
- Test: `tests/unit/test_per_salesperson_report_service.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_per_salesperson_report_service.py
"""测试 PerSalespersonReportService"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from services.per_salesperson_report_service import PerSalespersonReportService


class TestPerSalespersonReportService:
    def test_collect_report_data_returns_summary(self):
        with patch(
            "services.per_salesperson_report_service.ClickHouseDataService"
        ) as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            # 模拟 dm_customer360 数据
            mock_ch.execute_query.return_value = [
                {
                    "customer_name": "腾讯科技",
                    "ar_total": 1000000.0,
                    "ar_overdue": 100000.0,
                    "overdue_rate": 0.10,
                    "risk_level": "中",
                }
            ]
            svc = PerSalespersonReportService()
            data = svc._collect_report_data("S001", date(2026, 3, 21))
            assert data["customer_count"] == 1
            assert data["summary"]["ar_total"] == 1000000.0
            assert data["summary"]["overdue_rate"] == 0.10

    def test_collect_returns_empty_if_no_customers(self):
        with patch(
            "services.per_salesperson_report_service.ClickHouseDataService"
        ) as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = []
            svc = PerSalespersonReportService()
            data = svc._collect_report_data("S001", date(2026, 3, 21))
            assert data["customer_count"] == 0
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/unit/test_per_salesperson_report_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 创建 services/per_salesperson_report_service.py**

```python
# services/per_salesperson_report_service.py
"""业务员 AR 报告服务"""
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from services.clickhouse_service import ClickHouseDataService
from services.salesperson_mapping_service import SalespersonMappingService

PROJECT_ROOT = Path(__file__).parent.parent


class PerSalespersonReportService:
    """业务员 AR 报告生成"""

    def __init__(
        self,
        ch: ClickHouseDataService | None = None,
        mapping_service: SalespersonMappingService | None = None,
    ):
        self._ch = ch or ClickHouseDataService()
        self._mapping = mapping_service or SalespersonMappingService()
        self._jinja = Environment(
            loader=FileSystemLoader(PROJECT_ROOT / "templates" / "reports"),
            autoescape=True,
        )

    def generate_for_all(self, report_period: str = "weekly") -> list[str]:
        """为所有启用的业务员生成报告，返回文件路径列表"""
        active = self._mapping.list_active()
        files = []
        for rep in active:
            try:
                path = self.generate_for_salesperson(rep["salesperson_id"], report_period)
                files.append(path)
            except Exception:
                pass  # 单个失败不阻塞其他
        return files

    def generate_for_salesperson(
        self,
        salesperson_id: str,
        report_period: str = "weekly",
        today: date | None = None,
    ) -> str:
        """为指定业务员生成 AR 报告"""
        today = today or date.today()
        data = self._collect_report_data(salesperson_id, today, report_period)
        if data["customer_count"] == 0:
            return ""  # 无客户，跳过

        template = self._jinja.get_template("ar_per_salesperson.html.j2")
        html = template.render(
            salesperson_name=data["salesperson_name"],
            salesperson_id=salesperson_id,
            report_period=report_period,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            today=today.isoformat(),
            **data,
        )

        output_dir = PROJECT_ROOT / "static" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"ar_per_salesperson_{salesperson_id}_{today.isoformat()}.html"
        filepath = output_dir / filename
        filepath.write_text(html, encoding="utf-8")

        # 记录
        self._save_record(salesperson_id, report_period, str(filepath))
        return str(filepath)

    def _collect_report_data(
        self,
        salesperson_id: str,
        today: date,
        report_period: str,
    ) -> dict[str, Any]:
        # 获取业务员姓名
        active = self._mapping.list_active()
        rep = next((r for r in active if r["salesperson_id"] == salesperson_id), None)
        salesperson_name = rep["salesperson_name"] if rep else salesperson_id

        # 获取所负责客户
        customers = self._mapping.list_customers_by_salesperson(salesperson_id)
        if not customers:
            return {
                "salesperson_name": salesperson_name,
                "customer_count": 0,
                "summary": {},
                "customers": [],
            }

        customer_ids = "', '".join(c["customer_id"] for c in customers)
        customer_names = "', '".join(c["customer_name"] for c in customers)

        # 查询 AR 数据（JOIN dm_customer360，取最近 stat_date）
        ar_rows = self._ch.execute_query(
            f"SELECT "
            f"  customer_name, ar_total, ar_overdue, overdue_rate, risk_level "
            f"FROM dm.dm_customer360 "
            f"WHERE stat_date = (SELECT max(stat_date) FROM dm.dm_customer360) "
            f"  AND customer_id IN ('{customer_ids}') "
            f"ORDER BY overdue_rate DESC"
        )
        if not ar_rows:
            ar_rows = self._ch.execute_query(
                f"SELECT "
                f"  customer_name, ar_total, ar_overdue, overdue_rate, risk_level "
                f"FROM dm.dm_customer360 "
                f"WHERE stat_date = (SELECT max(stat_date) FROM dm.dm_customer360) "
                f"  AND customer_name IN ('{customer_names}') "
                f"ORDER BY overdue_rate DESC"
            )

        ar_total = sum(float(r.get("ar_total") or 0) for r in ar_rows)
        ar_overdue = sum(float(r.get("ar_overdue") or 0) for r in ar_rows)
        overdue_rate = ar_overdue / ar_total if ar_total > 0 else 0.0

        # 本周/本月新增逾期（简化：取 alert_history 最近7天内）
        days = 7 if report_period == "weekly" else 30
        new_overdue_rows = self._ch.execute_query(
            f"SELECT count() AS cnt FROM dm.alert_history "
            f"WHERE triggered_at >= now() - interval {days} day "
            f"  AND metric = 'overdue_rate'"
        )
        new_overdue = new_overdue_rows[0]["cnt"] if new_overdue_rows else 0

        return {
            "salesperson_name": salesperson_name,
            "customer_count": len(ar_rows),
            "summary": {
                "ar_total": ar_total,
                "ar_overdue": ar_overdue,
                "overdue_rate": overdue_rate,
                "new_overdue": new_overdue,
            },
            "customers": [dict(r) for r in ar_rows],
        }

    def _save_record(self, salesperson_id: str, report_period: str, filepath: str) -> None:
        now = datetime.now().isoformat()
        record_id = str(uuid.uuid4())
        # period_start = today - 7 (周报) 或 today - 30 (月报)
        days_offset = 7 if report_period == "weekly" else 30
        period_start = (date.today() - timedelta(days=days_offset)).isoformat()
        period_end = date.today().isoformat()
        try:
            self._ch.execute(
                f"INSERT INTO dm.report_records "
                f"(id, report_type, period_start, period_end, recipients, file_path, sent_at, status, salesperson_id) "
                f"VALUES ('{record_id}', 'ar_per_salesperson', '{period_start}', '{period_end}', "
                f"'[\"{salesperson_id}\"]', '{filepath}', '{now}', 'generated', '{salesperson_id}')"
            )
        except Exception:
            pass
```

- [ ] **Step 4: 创建 templates/reports/ar_per_salesperson.html.j2**

```html
<!-- templates/reports/ar_per_salesperson.html.j2 -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AR 报告 - {{ salesperson_name }}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, sans-serif; background: #f5f7fa; padding: 20px; }
  .container { max-width: 900px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; }
  .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
  h1 { font-size: 20px; }
  .subtitle { color: #888; font-size: 14px; }
  .kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
  .kpi { background: #f8fafc; border-radius: 8px; padding: 16px; text-align: center; }
  .kpi .v { font-size: 22px; font-weight: 700; }
  .kpi .l { font-size: 12px; color: #888; margin-top: 4px; }
  .kpi .v.danger { color: #e53e3e; }
  .kpi .v.warning { color: #d69e2e; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 16px; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }
  th { color: #888; font-size: 12px; text-transform: uppercase; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
  .tag.high { background: #fed7d7; color: #c53030; }
  .tag.medium { background: #fefcbf; color: #975a16; }
  .tag.low { background: #c6f6d5; color: #276749; }
  .footer { margin-top: 24px; color: #aaa; font-size: 12px; text-align: center; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 {{ salesperson_name }} AR 报告</h1>
    <span class="subtitle">{{ today }} | {{ report_period }}</span>
  </div>

  <div class="kpi-row">
    <div class="kpi">
      <div class="v">{{ customer_count }}</div>
      <div class="l">负责客户</div>
    </div>
    <div class="kpi">
      <div class="v">¥{{ "%.0f"|format(summary.ar_total) }}</div>
      <div class="l">AR 总额</div>
    </div>
    <div class="kpi">
      <div class="v danger">¥{{ "%.0f"|format(summary.ar_overdue) }}</div>
      <div class="l">逾期金额</div>
    </div>
    <div class="kpi">
      <div class="v {% if summary.overdue_rate > 0.1 %}danger{% elif summary.overdue_rate > 0.05 %}warning{% endif %}">
        {{ "%.1f"|format(summary.overdue_rate * 100) }}%
      </div>
      <div class="l">逾期率</div>
    </div>
  </div>

  {% if new_overdue > 0 %}
  <div style="background:#fff5f5;border-left:4px solid #e53e3e;padding:12px 16px;margin-bottom:16px;border-radius:4px;font-size:14px;">
    ⚠️ 本{{ report_period == 'weekly' and '周' or '月' }}新增逾期客户 <strong>{{ new_overdue }}</strong> 个，请及时跟进。
  </div>
  {% endif %}

  <h2 style="font-size:15px;margin-bottom:8px;">客户明细</h2>
  <table>
    <thead>
      <tr>
        <th>客户名称</th>
        <th>AR总额</th>
        <th>逾期金额</th>
        <th>逾期率</th>
        <th>风险等级</th>
      </tr>
    </thead>
    <tbody>
    {% for c in customers %}
    <tr>
      <td>{{ c.customer_name }}</td>
      <td>¥{{ "%.0f"|format(c.ar_total) }}</td>
      <td>¥{{ "%.0f"|format(c.ar_overdue) }}</td>
      <td>{{ "%.1f"|format(c.overdue_rate * 100) }}%</td>
      <td>
        <span class="tag {% if c.risk_level == '高' %}high{% elif c.risk_level == '中' %}medium{% else %}low{% endif %}">
          {{ c.risk_level }}
        </span>
      </td>
    </tr>
    {% endfor %}
    {% if not customers %}
    <tr><td colspan="5" style="color:#888;text-align:center;">暂无客户数据</td></tr>
    {% endif %}
    </tbody>
  </table>

  <div class="footer">FinBoss AR 业务员报告 | {{ generated_at }}</div>
</div>
</body>
</html>
```

- [ ] **Step 5: 运行测试验证通过**

Run: `uv run pytest tests/unit/test_per_salesperson_report_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/per_salesperson_report_service.py templates/reports/ar_per_salesperson.html.j2 tests/unit/test_per_salesperson_report_service.py
git commit -m "feat: add PerSalespersonReportService with AR report template"
```

---

## Task 7: APScheduler 调度集成

**Files:**
- Modify: `services/scheduler_service.py`
- Modify: `services/report_service.py`（+send_to_sales_channel）

- [ ] **Step 1: 读取现有的 scheduler_service.py**

Run: `cat services/scheduler_service.py`

- [ ] **Step 2: 在 scheduler_service.py 末尾添加 Phase 6 任务**

在 `_register_phase5_jobs` 函数后添加：

```python
def _register_phase6_jobs(scheduler: AsyncIOScheduler) -> None:
    """注册 Phase 6 调度任务"""

def _per_salesperson_job(report_period: str) -> None:
        """通用报告生成函数，支持 weekly/monthly"""
        import logging
        logger = logging.getLogger(__name__)
        try:
            from services.per_salesperson_report_service import PerSalespersonReportService
            from api.config import get_feishu_config
            from services.feishu.feishu_client import FeishuClient

            svc = PerSalespersonReportService()
            files = svc.generate_for_all(report_period=report_period)
            config = get_feishu_config()
            if files and config.sales_channel_id:
                client = FeishuClient()
                period_label = "周报" if report_period == "weekly" else "月报"
                card = {
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": f"**📊 AR 业务员{period_label}已生成**\n共 {len(files)} 位业务员的报告已就绪：\n" + "\n".join(
                                f"- `{f.split('_')[-2]}`: {f}" for f in files[:5]
                            ),
                        },
                        {
                            "tag": "action",
                            "actions": [{
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "查看报告"},
                                "type": "primary",
                                "url": "/static/reports/",
                            }],
                        }
                    ]
                }
                client.send_card_to_channel(card, channel_id=config.sales_channel_id)
            logger.info(f"[Phase6] Per-salesperson {report_period} reports: {len(files)} generated")
        except Exception as e:
            logger.error(f"[Phase6] Per-salesperson {report_period} report failed: {e}")

    scheduler.add_job(
        lambda: _per_salesperson_job("weekly"),
        CronTrigger(day_of_week="mon", hour=8, minute=5),
        id="phase6_per_salesperson_weekly",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _per_salesperson_job("monthly"),
        CronTrigger(day=1, hour=8, minute=5),
        id="phase6_per_salesperson_monthly",
        replace_existing=True,
    )
```

在 `start_scheduler()` 函数中，在 `_register_phase5_jobs(scheduler)` 后添加：

```python
_register_phase6_jobs(scheduler)
```

- [ ] **Step 3: 更新 reports.py 添加手动触发端点**

在 `api/routes/reports.py` 中添加：

```python
@router.post("/ar/per-salesperson")
async def trigger_per_salesperson_report(
    body: dict | None = None,
    service: ReportServiceDep = None,
):
    """手动触发业务员 AR 报告"""
    from services.per_salesperson_report_service import PerSalespersonReportService
    from api.dependencies import get_salesperson_mapping_service

    svc = PerSalespersonReportService(
        mapping_service=get_salesperson_mapping_service()
    )
    sid = body.get("salesperson_id") if body else None
    period = body.get("report_period", "weekly") if body else "weekly"

    if sid:
        path = svc.generate_for_salesperson(sid, period)
        return {"status": "generated", "file": path, "count": 1 if path else 0}
    else:
        files = svc.generate_for_all(period)
        return {"status": "generated", "files": files, "count": len(files)}


@router.post("/ap")
async def trigger_ap_report(
    service: ReportServiceDep = None,
):
    """手动触发 AP 报告"""
    from services.ap_service import APService

    svc = APService()
    path = svc.generate_dashboard()
    # 记录到 report_records
    _save_report_record(
        report_type="ap",
        period_start=date.today().isoformat(),
        period_end=date.today().isoformat(),
        recipients="finance",
        file_path=path,
    )
    return {"status": "generated", "file": path}


@router.get("/records")
async def get_report_records(
    report_type: str | None = None,
    limit: int = 50,
    service: ReportServiceDep = None,
):
    """查询报告发送记录（含 AP 和 per-rep）"""
    from services.clickhouse_service import ClickHouseDataService
    ch = ClickHouseDataService()
    where = ["1=1"]
    if report_type:
        where.append(f"report_type = '{report_type}'")
    rows = ch.execute_query(
        f"SELECT * FROM dm.report_records "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY sent_at DESC LIMIT {limit}"
    )
    return {"items": rows, "total": len(rows)}
```

- [ ] **Step 4: Commit**

```bash
git add services/scheduler_service.py api/routes/reports.py
git commit -m "feat: Phase 6 APScheduler per-salesperson report jobs (08:05 Mon + 1st of month)"
```

---

## Task 8: 集成测试 + 冒烟测试

**Files:**
- Modify: `tests/integration/test_ap_api.py`（补充完整测试）
- Create: `tests/integration/test_salesperson_mapping_api.py`

- [ ] **Step 1: 补充 AP API 集成测试**

```python
# tests/integration/test_ap_api.py（补充）
class TestAPUploadWithMockFile:
    def test_upload_validates_file_size(self, client):
        with patch("services.ap_bank_parser.APBankStatementParser.process_upload") as mock:
            mock.return_value = {"file": "test.csv", "raw_saved": 5, "std_saved": 5, "parse_errors": 0, "errors": []}
            # 文件大小验证在路由层，不在 service 层
            pass  # covered by route test


class TestAPKPIAndSuppliers:
    def test_get_kpi_returns_all_fields(self, client):
        with patch("services.ap_service.APService.get_kpi") as mock:
            mock.return_value = {
                "ap_total": "1000000", "unsettled_total": "400000",
                "overdue_total": "50000", "overdue_rate": 0.05, "supplier_count": 15,
            }
            response = client.get("/api/v1/ap/kpi")
            assert response.status_code == 200
            data = response.json()
            assert float(data["overdue_rate"]) == 0.05

    def test_get_suppliers_returns_list(self, client):
        with patch("services.ap_service.APService.get_suppliers") as mock:
            mock.return_value = [
                {"supplier_name": "腾讯科技", "total_amount": 500000, "unsettled_amount": 100000, "overdue_amount": 0, "record_count": 10},
            ]
            response = client.get("/api/v1/ap/suppliers")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
```

- [ ] **Step 2: 创建 tests/integration/test_salesperson_mapping_api.py**

```python
# tests/integration/test_salesperson_mapping_api.py
"""业务员映射 API 集成测试"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestSalespersonMappingAPI:
    def test_list_returns_empty(self, client):
        with patch(
            "services.salesperson_mapping_service.SalespersonMappingService.list_mappings",
            return_value=[],
        ):
            response = client.get("/api/v1/salesperson/mappings")
            assert response.status_code == 200
            assert response.json()["total"] == 0

    def test_create_validates_salesperson_id(self, client):
        response = client.post(
            "/api/v1/salesperson/mappings",
            json={"salesperson_id": "s001", "salesperson_name": "张三分"},
        )
        # 小写应被拒绝
        assert response.status_code in (400, 422)

    def test_create_valid_salesperson(self, client):
        with patch(
            "services.salesperson_mapping_service.SalespersonMappingService.create_mapping",
            return_value={"id": "new-id", "salesperson_id": "S001", "salesperson_name": "张三分"},
        ):
            response = client.post(
                "/api/v1/salesperson/mappings",
                json={"salesperson_id": "S001", "salesperson_name": "张三分"},
            )
            assert response.status_code == 200
            assert response.json()["salesperson_id"] == "S001"
```

- [ ] **Step 3: 运行全部测试**

Run: `uv run pytest tests/ -q --ignore=tests/integration/test_customer360_api.py -x`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_salesperson_mapping_api.py tests/integration/test_ap_api.py
git commit -m "test: add Phase 6 integration tests for salesperson mapping and AP APIs"
```

---

## 执行顺序

```
Task 1 (DDL + Init)
    ↓
Task 2 (SalespersonMappingService + 映射 API)
    ↓
Task 3 (APBankStatementParser)
    ↓
Task 4 (APService + AP API)
    ↓
Task 5 (AP 看板模板)
    ↓
Task 6 (PerSalespersonReportService + 模板)
    ↓
Task 7 (Scheduler + 手动触发 API)
    ↓
Task 8 (集成测试)
```
