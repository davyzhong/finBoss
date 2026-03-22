from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from schemas.quality import AnomalyStatus


class QualitySummaryResponse(BaseModel):
    stat_date: date
    total_tables: int
    total_fields: int
    anomaly_count: int
    high_severity: int
    medium_severity: int
    score_pct: float
    last_check_at: datetime | None


class AnomalyUpdateRequest(BaseModel):
    status: Literal["resolved", "ignored"]
    note: str | None = None


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
