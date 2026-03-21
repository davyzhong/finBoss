"""AR 相关 API Schema"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ARSummaryResponse(BaseModel):
    """AR 汇总响应"""

    stat_date: datetime
    company_code: str
    company_name: str
    total_ar_amount: float = Field(description="应收总额")
    received_amount: float = Field(description="已收金额")
    allocated_amount: float = Field(description="已核销金额")
    unallocated_amount: float = Field(description="未核销金额")
    overdue_amount: float = Field(description="逾期金额")
    overdue_count: int = Field(description="逾期单数")
    total_count: int = Field(description="应收单总数")
    overdue_rate: float = Field(description="逾期率")
    aging_0_30: float = Field(description="0-30天应收")
    aging_31_60: float = Field(description="31-60天应收")
    aging_61_90: float = Field(description="61-90天应收")
    aging_91_180: float = Field(description="91-180天应收")
    aging_180_plus: float = Field(description="180天以上应收")
    etl_time: datetime


class CustomerARResponse(BaseModel):
    """客户 AR 响应"""

    stat_date: datetime
    customer_code: str
    customer_name: str
    company_code: str
    total_ar_amount: float
    overdue_amount: float
    overdue_count: int
    total_count: int
    overdue_rate: float
    last_bill_date: Optional[datetime]
    etl_time: datetime


class ARDetailResponse(BaseModel):
    """AR 明细响应"""

    id: str
    stat_date: datetime
    company_code: str
    company_name: str
    customer_code: str
    customer_name: str
    bill_no: str
    bill_date: datetime
    due_date: Optional[datetime]
    bill_amount: float
    received_amount: float
    allocated_amount: float
    unallocated_amount: float
    aging_bucket: str
    aging_days: int
    is_overdue: bool
    overdue_days: int
    status: str
    etl_time: datetime


class QualityCheckRequest(BaseModel):
    """质量检查请求"""

    table_name: str = Field(description="表名")
    max_delay_minutes: int = Field(default=10, description="最大延迟分钟数")
    rules: list[dict] = Field(default_factory=list, description="质量检查规则列表")


class QualityCheckResponse(BaseModel):
    """质量检查响应"""

    table_name: str
    check_time: datetime
    latest_update: datetime | None
    passed: int
    total_rules: int
    passed_rules: int
    failed_rules: int
    details: list[dict]
