from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class CheckResponse(BaseModel):
    status: str
    report_count: int
    anomaly_count: int
    duration_ms: int


class QualitySummaryResponse(BaseModel):
    stat_date: date
    total_tables: int
    total_fields: int
    anomaly_count: int
    high_severity: int
    medium_severity: int
    score_pct: float
    score_trend: str  # "improving ↓" | "stable →" | "degrading ↑"
    overdue_count: int  # open anomalies past SLA
    last_check_at: datetime | None


class QualityHistoryPoint(BaseModel):
    stat_date: date
    score_pct: float
    anomaly_count: int
    high_severity: int
    medium_severity: int


class QualityHistoryResponse(BaseModel):
    points: list[QualityHistoryPoint]
    score_trend: str  # "improving ↓" | "stable →" | "degrading ↑"


class AnomalyUpdateRequest(BaseModel):
    status: Literal["resolved", "ignored"] | None = None
    assignee: str | None = None
    note: str | None = None


class SendDigestResponse(BaseModel):
    status: str
    email_sent: int
    dingtalk_sent: int


class RootCauseAnalysisResponse(BaseModel):
    anomaly_id: str
    root_cause: str
    suggestions: list[str]
    confidence: Literal["high", "medium", "low"]
    model_used: str
    analyzed_at: datetime


class AggregatedAnomalyItem(BaseModel):
    id: str
    table_name: str
    column_name: str
    severity: str
    status: str
    assignee: str
    created_at: date


class AggregatedAnomalyGroup(BaseModel):
    key: str
    total: int
    high: int
    medium: int
    low: int
    unassigned: int
    oldest_age_days: int
    items: list[AggregatedAnomalyItem]


class AggregatedAnomaliesResponse(BaseModel):
    groups: list[AggregatedAnomalyGroup]
    total_anomalies: int
