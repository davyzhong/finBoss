"""数据质量 API 路由"""
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import FieldQualityServiceDep
from api.schemas.quality import (
    AnomalyUpdateRequest,
    CheckResponse,
    QualityHistoryResponse,
    QualitySummaryResponse,
    SendDigestResponse,
)

router = APIRouter(tags=["quality"])


@router.get("/summary", response_model=QualitySummaryResponse)
async def get_quality_summary(service: FieldQualityServiceDep):
    """全局健康度概览"""
    return service.get_summary()


@router.get("/reports")
async def list_reports(
    service: FieldQualityServiceDep,
    stat_date: date | None = Query(default=None),
    limit: int = Query(default=50, le=500),
):
    """质量报告列表"""
    stat_date = stat_date or date.today()
    rows = service.list_reports(stat_date, limit)
    return {"items": rows, "total": len(rows)}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, service: FieldQualityServiceDep):
    """报告详情（含异常明细）"""
    report = service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    anomalies = service.list_anomalies_by_report(report_id)
    return {"report": report, "anomalies": anomalies}


@router.get("/anomalies")
async def list_anomalies(
    service: FieldQualityServiceDep,
    status: Literal["open", "resolved", "ignored"] | None = Query(default=None),
    assignee: str | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
):
    """异常列表（默认返回 open，可按 status / assignee 筛选）"""
    rows = service.list_anomalies(status, limit, assignee)
    return {"items": rows, "total": len(rows)}


@router.put("/anomalies/{anomaly_id}")
async def update_anomaly(
    anomaly_id: str,
    body: AnomalyUpdateRequest,
    service: FieldQualityServiceDep,
):
    """标记异常状态或分配负责人"""
    service.update_anomaly(anomaly_id, status=body.status, assignee=body.assignee)
    new_status = body.status or "updated"
    return {"status": "updated", "id": anomaly_id, "new_status": new_status}


@router.get("/history", response_model=QualityHistoryResponse)
async def get_quality_history(
    service: FieldQualityServiceDep,
    days: int = Query(default=7, ge=3, le=90),
):
    """过去 N 天的质量趋势数据（默认 7 天）"""
    points = service.get_quality_history(days)
    current_score = service.get_summary().get("score_pct", 100)
    trend = service._compute_score_trend(date.today(), current_score)
    return QualityHistoryResponse(points=points, score_trend=trend)


@router.post("/send-digest", response_model=SendDigestResponse)
async def send_quality_digest(service: FieldQualityServiceDep):
    """手动触发质量摘要邮件/钉钉推送"""
    result = service.send_quality_digest()
    return SendDigestResponse(
        status="ok",
        email_sent=result["email_sent"],
        dingtalk_sent=result["dingtalk_sent"],
    )


@router.post("/check", response_model=CheckResponse)
async def trigger_check(service: FieldQualityServiceDep):
    """手动触发一次质量检查"""
    import time
    start = time.monotonic()
    result = service.check_all()
    service.send_feishu_card()
    duration_ms = int((time.monotonic() - start) * 1000)
    return CheckResponse(
        status="ok",
        report_count=result["total_tables"],
        anomaly_count=result["anomaly_count"],
        duration_ms=duration_ms,
    )
