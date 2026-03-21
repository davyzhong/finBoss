"""归因分析 API 路由"""
from fastapi import APIRouter
from pydantic import BaseModel

from api.dependencies import AttributionServiceDep
from schemas.attribution import AttributionResult

router = APIRouter()


class AttributionRequest(BaseModel):
    question: str


@router.post("/analyze", response_model=AttributionResult)
async def analyze(
    question: AttributionRequest,
    service: AttributionServiceDep,
) -> AttributionResult:
    """归因分析

    分析财务指标异动原因，返回 Top 归因因子。

    示例问题:
    - "为什么本月逾期率上升了"
    - "为什么收入下降了"
    """
    return service.analyze(question.question)
