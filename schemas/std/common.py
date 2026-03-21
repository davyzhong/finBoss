# schemas/std/common.py
"""标准层通用模型"""
from datetime import datetime

from pydantic import BaseModel, Field


class StdBaseRecord(BaseModel):
    """标准层基础记录"""

    id: str = Field(description="主键 UUID")
    stat_date: datetime = Field(description="统计日期")
    etl_time: datetime = Field(description="ETL处理时间")
    source_system: str = Field(default="unknown", description="来源系统")
    source_table: str = Field(default="", description="来源表")

    class Config:
        from_attributes = True
