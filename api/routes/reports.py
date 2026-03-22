"""报告 API 路由"""
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Body, Depends

from services.dashboard_service import DashboardService
from services.report_service import ReportService

router = APIRouter(tags=["reports"])


@lru_cache
def get_report_service() -> ReportService:
    return ReportService()


@lru_cache
def get_dashboard_service() -> DashboardService:
    return DashboardService()


ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]
DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]


@router.post("/weekly")
async def trigger_weekly(service: ReportServiceDep):
    """手动触发周报生成"""
    path = service.generate("weekly")
    return {"status": "generated", "file": path}


@router.post("/monthly")
async def trigger_monthly(service: ReportServiceDep):
    """手动触发生成月报"""
    path = service.generate("monthly")
    return {"status": "generated", "file": path}


@router.get("/records")
async def list_records(service: ReportServiceDep, limit: int = 50):
    """查询报告发送记录（含 AP 和 per-rep）"""
    rows = service._ch.execute_query(
        f"SELECT * FROM dm.report_records ORDER BY sent_at DESC LIMIT {min(limit, 1000)}"
    )
    return {"items": rows, "total": len(rows)}


@router.post("/dashboard/generate")
async def generate_dashboard(service: DashboardServiceDep):
    """手动生成看板"""
    path = service.generate()
    return {"status": "generated", "file": path}


# --- Phase 6 endpoints ---


@router.post("/ar/per-salesperson")
async def trigger_per_salesperson_report(
    body: dict | None = Body(default=None),
):
    """手动触发业务员 AR 报告"""
    from services.per_salesperson_report_service import PerSalespersonReportService

    svc = PerSalespersonReportService()
    sid = body.get("salesperson_id") if body else None
    period = body.get("report_period", "weekly") if body else "weekly"

    if sid:
        path = svc.generate_for_salesperson(sid, period)
        return {"status": "generated", "file": path, "count": 1 if path else 0}
    else:
        files = svc.generate_for_all(period)
        return {"status": "generated", "files": files, "count": len(files)}


@router.post("/ap")
async def trigger_ap_report():
    """手动触发 AP 报告"""
    from services.ap_service import APService

    svc = APService()
    path = svc.generate_dashboard()
    return {"status": "generated", "file": path}
