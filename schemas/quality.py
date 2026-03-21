from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel


class Severity(str, Enum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class AnomalyStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class QualityMetric(str, Enum):
    NULL_RATE = "null_rate"
    DISTINCT_RATE = "distinct_rate"
    NEGATIVE_RATE = "negative_rate"
    FRESHNESS_HOURS = "freshness_hours"


class QualityAnomaly(BaseModel):
    id: str
    report_id: str
    stat_date: date
    table_name: str
    column_name: str
    metric: QualityMetric
    value: float
    threshold: float
    severity: Severity
    status: AnomalyStatus = AnomalyStatus.OPEN
    detected_at: datetime
    resolved_at: datetime | None = None


class QualityReport(BaseModel):
    id: str
    stat_date: date
    table_name: str
    total_fields: int
    anomaly_count: int
    score_pct: float
    generated_at: datetime
