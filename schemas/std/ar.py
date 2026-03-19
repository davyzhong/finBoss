# schemas/std/ar.py
"""标准层 AR 应收模型"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class StdARRecord(BaseModel):
    """标准层应收记录"""

    id: str = Field(description="主键 UUID")
    stat_date: datetime = Field(description="统计日期")
    company_code: str = Field(description="公司编码")
    company_name: str = Field(description="公司名称")
    customer_code: str = Field(description="客户编码")
    customer_name: str = Field(description="客户名称")
    bill_no: str = Field(description="应收单号")
    bill_date: datetime = Field(description="应收日期")
    due_date: Optional[datetime] = Field(default=None, description="到期日期")
    bill_amount: float = Field(description="应收金额")
    received_amount: float = Field(description="已收金额")
    allocated_amount: float = Field(description="已核销金额")
    unallocated_amount: float = Field(description="未核销金额")
    currency: str = Field(default="CNY", description="币种")
    exchange_rate: float = Field(default=1.0, description="汇率")
    bill_amount_base: float = Field(description="应收金额(本位币)")
    received_amount_base: float = Field(description="已收金额(本位币)")
    aging_bucket: str = Field(description="账龄区间")
    aging_days: int = Field(description="账龄天数")
    is_overdue: bool = Field(description="是否逾期")
    overdue_days: int = Field(default=0, description="逾期天数")
    status: str = Field(description="状态")
    document_status: str = Field(description="审批状态")
    employee_name: Optional[str] = Field(default=None, description="业务员")
    dept_name: Optional[str] = Field(default=None, description="部门")
    etl_time: datetime = Field(description="ETL处理时间")

    class Config:
        from_attributes = True
