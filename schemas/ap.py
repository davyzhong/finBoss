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
