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
    last_payment_date: date | None = None
    first_coop_date: date | None = None
    company_code: str | None = None
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
    top10_ar_customers: list[dict] = Field(default_factory=list)


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
