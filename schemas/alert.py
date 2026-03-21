"""预警数据模型"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AlertLevel(str, Enum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class AlertOperator(str, Enum):
    GT = "gt"   # >
    LT = "lt"   # <
    GTE = "gte" # >=
    LTE = "lte" # <=


class AlertMetric(str, Enum):
    OVERDUE_RATE = "overdue_rate"
    OVERDUE_AMOUNT = "overdue_amount"
    OVERDUE_RATE_DELTA = "overdue_rate_delta"
    NEW_OVERDUE_COUNT = "new_overdue_count"
    AGING_90PCT = "aging_90pct"


class AlertRule(BaseModel):
    """预警规则配置"""
    id: str
    name: str
    metric: AlertMetric | str
    operator: AlertOperator | str
    threshold: float
    scope_type: str = "company"  # company / customer / sales
    scope_value: str | None = None
    alert_level: AlertLevel
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AlertHistory(BaseModel):
    """预警触发历史"""
    id: str
    rule_id: str
    rule_name: str
    alert_level: AlertLevel | str
    metric: str
    operator: str
    metric_value: float
    threshold: float
    scope_type: str = "company"
    scope_value: str | None = None
    triggered_at: datetime | None = None
    sent: int = 0  # 0=未发送, 1=已发送

    @property
    def exceeded(self) -> bool:
        """是否超过阈值"""
        if self.operator == "gt":
            return self.metric_value > self.threshold
        elif self.operator == "lt":
            return self.metric_value < self.threshold
        elif self.operator == "gte":
            return self.metric_value >= self.threshold
        elif self.operator == "lte":
            return self.metric_value <= self.threshold
        return False
