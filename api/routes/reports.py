"""报告 API 路由"""
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

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
async def list_records(service: ReportServiceDep, limit: int = 20):
    """查询报告发送记录"""
    rows = service._ch.execute_query(
        "SELECT * FROM dm.report_records ORDER BY sent_at DESC LIMIT %(limit)s",
        {"limit": min(limit, 1000)}
    )
    return {"items": rows, "total": len(rows)}


@router.post("/dashboard/generate")
async def generate_dashboard(service: DashboardServiceDep):
    """手动生成看板"""
    path = service.generate()
    return {"status": "generated", "file": path}
