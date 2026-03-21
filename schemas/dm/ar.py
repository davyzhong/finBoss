# schemas/dm/ar.py
"""数据集市层 AR 模型"""
from datetime import datetime

from pydantic import BaseModel, Field


class DMARSummary(BaseModel):
    """AR 应收汇总数据集"""

    stat_date: datetime = Field(description="统计日期")
    company_code: str = Field(description="公司编码")
    company_name: str = Field(description="公司名称")
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
    etl_time: datetime = Field(description="ETL处理时间")

    class Config:
        from_attributes = True


class DMCustomerAR(BaseModel):
    """客户维度 AR 汇总"""

    stat_date: datetime = Field(description="统计日期")
    customer_code: str = Field(description="客户编码")
    customer_name: str = Field(description="客户名称")
    company_code: str = Field(description="公司编码")
    total_ar_amount: float = Field(description="应收总额")
    overdue_amount: float = Field(description="逾期金额")
    overdue_count: int = Field(description="逾期单数")
    total_count: int = Field(description="应收单总数")
    overdue_rate: float = Field(description="逾期率")
    last_bill_date: datetime | None = Field(default=None, description="最近应收日期")
    etl_time: datetime = Field(description="ETL处理时间")

    class Config:
        from_attributes = True
