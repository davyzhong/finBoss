"""AP API 请求/响应模型"""
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
