"""AR 应收路由"""
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import ClickHouseServiceDep, QualityServiceDep
from api.schemas.ar import (
    ARDetailResponse,
    ARSummaryResponse,
    CustomerARResponse,
    QualityCheckRequest,
    QualityCheckResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary", response_model=list[ARSummaryResponse])
async def get_ar_summary(
    clickhouse_service: ClickHouseServiceDep,
    company_code: str | None = Query(default=None, description="公司编码"),
    stat_date: str | None = Query(default=None, description="统计日期 YYYY-MM-DD"),
):
    """获取 AR 汇总数据

    Args:
        clickhouse_service: ClickHouse 数据服务
        company_code: 公司编码（可选）
        stat_date: 统计日期（可选）

    Returns:
        AR 汇总数据列表
    """
    try:
        results = clickhouse_service.get_ar_summary(
            company_code=company_code,
            stat_date=stat_date,
        )
        return results
    except Exception:
        logger.exception("get_ar_summary failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/customer", response_model=list[CustomerARResponse])
async def get_customer_ar(
    clickhouse_service: ClickHouseServiceDep,
    customer_code: str | None = Query(default=None, description="客户编码"),
    is_overdue: bool | None = Query(default=None, description="是否逾期"),
    limit: int = Query(default=100, ge=1, le=1000, description="返回条数"),
):
    """获取客户 AR 汇总

    Args:
        clickhouse_service: ClickHouse 数据服务
        customer_code: 客户编码（可选）
        is_overdue: 是否逾期（可选）
        limit: 返回条数

    Returns:
        客户 AR 汇总列表
    """
    try:
        results = clickhouse_service.get_customer_ar(
            customer_code=customer_code,
            is_overdue=is_overdue,
            limit=limit,
        )
        return results
    except Exception:
        logger.exception("get_customer_ar failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/detail", response_model=list[ARDetailResponse])
async def get_ar_detail(
    clickhouse_service: ClickHouseServiceDep,
    bill_no: str | None = Query(default=None, description="应收单号"),
    customer_code: str | None = Query(default=None, description="客户编码"),
    company_code: str | None = Query(default=None, description="公司编码"),
    is_overdue: bool | None = Query(default=None, description="是否逾期"),
    limit: int = Query(default=100, ge=1, le=1000, description="返回条数"),
):
    """获取 AR 应收明细

    Args:
        clickhouse_service: ClickHouse 数据服务
        bill_no: 应收单号（可选）
        customer_code: 客户编码（可选）
        company_code: 公司编码（可选）
        is_overdue: 是否逾期（可选）
        limit: 返回条数

    Returns:
        AR 明细列表
    """
    try:
        results = clickhouse_service.get_ar_detail(
            bill_no=bill_no,
            customer_code=customer_code,
            company_code=company_code,
            is_overdue=is_overdue,
            limit=limit,
        )
        return results
    except Exception:
        logger.exception("get_ar_detail failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/quality-check", response_model=QualityCheckResponse)
async def check_ar_quality(
    clickhouse_service: ClickHouseServiceDep,
    quality_service: QualityServiceDep,
    request: QualityCheckRequest,
):
    """执行 AR 数据质量检查

    Args:
        clickhouse_service: ClickHouse 数据服务
        quality_service: 质量服务
        request: 质量检查请求

    Returns:
        质量检查结果
    """
    try:
        # 从目标表查询实际的最新 ETL 时间
        try:
            latest_update = clickhouse_service.get_latest_etl_time(request.table_name)
        except Exception:
            # 如果无法获取，抛出明确的错误
            raise HTTPException(
                status_code=400,
                detail=f"无法获取表 {request.table_name} 的最新更新时间，请确认表是否存在",
            )

        # 执行质量检查
        result = quality_service.check_table_quality(
            table_name=request.table_name,
            rules=request.rules,
            latest_update=latest_update,
        )

        return QualityCheckResponse(
            table_name=request.table_name,
            check_time=datetime.now(),
            latest_update=latest_update,
            total_rules=result["total_rules"],
            passed_count=result["passed"],
            failed_count=result["failed_rules"] + result.get("warnings", 0),
            details=result["details"],
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("check_ar_quality failed")
        raise HTTPException(status_code=500, detail="Internal server error")
