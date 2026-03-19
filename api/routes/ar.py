"""AR 应收路由"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import ARServiceDep, DataServiceDep, QualityServiceDep
from api.schemas.ar import (
    ARDetailResponse,
    ARSummaryResponse,
    CustomerARResponse,
    QualityCheckRequest,
    QualityCheckResponse,
)

router = APIRouter()


@router.get("/summary", response_model=list[ARSummaryResponse])
async def get_ar_summary(
    company_code: Optional[str] = Query(default=None, description="公司编码"),
    stat_date: Optional[str] = Query(default=None, description="统计日期 YYYY-MM-DD"),
    data_service: DataServiceDep,
):
    """获取 AR 汇总数据

    Args:
        company_code: 公司编码（可选）
        stat_date: 统计日期（可选）
        data_service: 数据服务

    Returns:
        AR 汇总数据列表
    """
    try:
        results = data_service.get_ar_summary(
            company_code=company_code,
            stat_date=stat_date,
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customer", response_model=list[CustomerARResponse])
async def get_customer_ar(
    customer_code: Optional[str] = Query(default=None, description="客户编码"),
    is_overdue: Optional[bool] = Query(default=None, description="是否逾期"),
    limit: int = Query(default=100, ge=1, le=1000, description="返回条数"),
    data_service: DataServiceDep,
):
    """获取客户 AR 汇总

    Args:
        customer_code: 客户编码（可选）
        is_overdue: 是否逾期（可选）
        limit: 返回条数
        data_service: 数据服务

    Returns:
        客户 AR 汇总列表
    """
    try:
        results = data_service.get_customer_ar(
            customer_code=customer_code,
            is_overdue=is_overdue,
            limit=limit,
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/detail", response_model=list[ARDetailResponse])
async def get_ar_detail(
    bill_no: Optional[str] = Query(default=None, description="应收单号"),
    customer_code: Optional[str] = Query(default=None, description="客户编码"),
    company_code: Optional[str] = Query(default=None, description="公司编码"),
    is_overdue: Optional[bool] = Query(default=None, description="是否逾期"),
    limit: int = Query(default=100, ge=1, le=1000, description="返回条数"),
    data_service: DataServiceDep,
):
    """获取 AR 应收明细

    Args:
        bill_no: 应收单号（可选）
        customer_code: 客户编码（可选）
        company_code: 公司编码（可选）
        is_overdue: 是否逾期（可选）
        limit: 返回条数
        data_service: 数据服务

    Returns:
        AR 明细列表
    """
    try:
        results = data_service.get_ar_detail(
            bill_no=bill_no,
            customer_code=customer_code,
            company_code=company_code,
            is_overdue=is_overdue,
            limit=limit,
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quality-check", response_model=QualityCheckResponse)
async def check_ar_quality(
    request: QualityCheckRequest,
    data_service: DataServiceDep,
    quality_service: QualityServiceDep,
):
    """执行 AR 数据质量检查

    Args:
        request: 质量检查请求
        data_service: 数据服务
        quality_service: 质量服务

    Returns:
        质量检查结果
    """
    try:
        # 这里简化实现，实际应从元数据服务获取最新更新时间
        latest_update = datetime.now()

        # 及时性检查
        timeliness_result = quality_service.check_timeliness(
            table_name=request.table_name,
            latest_update=latest_update,
            max_delay_minutes=request.max_delay_minutes,
        )
        quality_service.add_result(timeliness_result)

        return quality_service.get_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
