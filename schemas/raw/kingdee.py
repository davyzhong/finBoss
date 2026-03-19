# schemas/raw/kingdee.py
"""原始层 Schema - 与金蝶数据库表一一映射"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RawARVerify(BaseModel):
    """原始层应收单"""

    id: str = Field(description="主键 UUID")
    source_system: str = Field(default="kingdee", description="来源系统")
    source_table: str = Field(default="t_ar_verify", description="来源表")
    source_id: int = Field(description="来源记录ID")
    bill_no: str = Field(description="单据编号")
    bill_date: datetime = Field(description="单据日期")
    customer_id: int = Field(description="客户ID")
    customer_name: str = Field(description="客户名称")
    bill_amount: float = Field(description="单据金额")
    payment_amount: float = Field(description="已付款金额")
    allocate_amount: float = Field(description="已核销金额")
    unallocate_amount: float = Field(description="未核销金额")
    status: str = Field(description="状态")
    company_id: int = Field(description="公司ID")
    dept_id: Optional[int] = Field(default=None, description="部门ID")
    employee_id: Optional[int] = Field(default=None, description="业务员ID")
    document_status: str = Field(description="审批状态")
    creator_id: Optional[int] = Field(default=None, description="创建人ID")
    create_time: datetime = Field(description="创建时间")
    update_time: Optional[datetime] = Field(default=None, description="更新时间")
    etl_time: datetime = Field(description="ETL处理时间")

    class Config:
        from_attributes = True
