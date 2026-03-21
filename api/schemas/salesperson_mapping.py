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
