# api/routes/customer360.py
"""客户360 API 路由"""
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import Customer360ServiceDep
from api.schemas.customer360 import (
    UndoMergeRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/customer360", tags=["客户360"])


@router.get("/summary")
async def get_customer360_summary(service: Customer360ServiceDep):
    """管理层视角客户汇总"""
    try:
        return service.get_summary()
    except Exception as e:
        logger.error(f"获取客户360汇总失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/distribution")
async def get_customer360_distribution(
    service: Customer360ServiceDep,
    stat_date: str | None = Query(None, description="统计日期 YYYY-MM-DD"),
):
    """客户分布数据（用于图表）"""
    try:
        d = date.fromisoformat(stat_date) if stat_date else date.today()
        return service.get_distribution(d)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的日期格式，请使用 YYYY-MM-DD")
    except Exception as e:
        logger.error(f"获取客户分布失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trend")
async def get_customer360_trend(
    service: Customer360ServiceDep,
    months: int = Query(12, ge=1, le=24, description="查询月数"),
):
    """客户/应收趋势（近N个月）"""
    try:
        return service.get_trend(months)
    except Exception as e:
        logger.error(f"获取趋势数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{customer_code}/detail")
async def get_customer_detail(
    customer_code: str,
    service: Customer360ServiceDep,
):
    """单个客户360详情"""
    detail = service.get_customer_detail(customer_code)
    if not detail:
        raise HTTPException(status_code=404, detail="客户不存在")
    return detail


@router.get("/merge-queue")
async def get_merge_queue(
    service: Customer360ServiceDep,
    status: str = Query("pending", description="筛选状态"),
):
    """合并复核队列"""
    items = service.get_merge_queue(status)
    return {
        "items": [
            {
                "id": item.id,
                "similarity": item.match_result.similarity,
                "reason": item.match_result.reason,
                "customers": [
                    {
                        "customer_id": c.customer_id,
                        "name": c.customer_name,
                        "source": c.source_system,
                    }
                    for c in item.match_result.customers
                ],
                "unified_customer_code": item.match_result.unified_customer_code,
                "status": item.status,
                "created_at": item.match_result.created_at.isoformat() if item.match_result.created_at else None,
            }
            for item in items
        ],
        "total": len(items),
    }


@router.post("/merge-queue/{queue_id}/confirm")
async def confirm_merge(
    queue_id: str,
    service: Customer360ServiceDep,
):
    """确认合并"""
    result = service.confirm_merge(queue_id)
    return result


@router.post("/merge-queue/{queue_id}/reject")
async def reject_merge(
    queue_id: str,
    service: Customer360ServiceDep,
):
    """拒绝合并"""
    result = service.reject_merge(queue_id)
    return result


@router.post("/{customer_code}/undo")
async def undo_merge(
    customer_code: str,
    request: UndoMergeRequest,
    service: Customer360ServiceDep,
):
    """撤销合并"""
    result = service.undo_merge(
        unified_customer_code=customer_code,
        original_customer_id=request.original_customer_id,
        reason=request.reason,
    )
    return result


@router.get("/attribution")
async def get_attribution_data(
    service: Customer360ServiceDep,
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
):
    """AI 归因数据接口"""
    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的日期格式")
    return service.get_attribution_data(sd, ed)
