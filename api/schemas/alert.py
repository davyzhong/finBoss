"""预警 API 请求/响应模型"""
from datetime import datetime
from pydantic import BaseModel, Field


class AlertRuleCreate(BaseModel):
    name: str
    metric: str
    operator: str
    threshold: float
    scope_type: str = "company"
    scope_value: str | None = None
    alert_level: str
    enabled: bool = True


class AlertRuleResponse(BaseModel):
    id: str
    name: str
    metric: str
    operator: str
    threshold: float
    scope_type: str
    scope_value: str | None
    alert_level: str
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None


class AlertHistoryResponse(BaseModel):
    id: str
    rule_id: str
    rule_name: str
    alert_level: str
    metric: str
    operator: str
    metric_value: float
    threshold: float
    scope_type: str
    scope_value: str | None
    triggered_at: datetime
    sent: int
