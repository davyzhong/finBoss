"""查询相关 API Schema"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """通用查询请求"""

    sql: str = Field(description="SQL 查询语句")
    params: Optional[dict[str, Any]] = Field(default=None, description="查询参数")


class QueryResponse(BaseModel):
    """通用查询响应"""

    data: list[dict[str, Any]]
    row_count: int
    execution_time_ms: float


class StatDateRequest(BaseModel):
    """统计日期请求"""

    stat_date: Optional[str] = Field(default=None, description="统计日期 YYYY-MM-DD")


class CompanyCodeRequest(BaseModel):
    """公司编码请求"""

    company_code: Optional[str] = Field(default=None, description="公司编码")


class CustomerCodeRequest(BaseModel):
    """客户编码请求"""

    customer_code: Optional[str] = Field(default=None, description="客户编码")
