# api/schemas/customer360.py
"""客户360 API 请求/响应模型"""
from typing import Any, Literal

from pydantic import BaseModel


class ConfirmActionRequest(BaseModel):
    action: Literal["confirm"] = "confirm"


class RejectActionRequest(BaseModel):
    action: Literal["reject"] = "reject"


class UndoMergeRequest(BaseModel):
    original_customer_id: str
    reason: str = ""


class AttributionDataResponse(BaseModel):
    dimension: str
    data: list[dict[str, Any]]
