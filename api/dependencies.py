"""依赖注入"""

from typing import Annotated

from fastapi import Depends

from api.config import Settings, get_settings
from services.ai import NLQueryService, RAGService
from services.ai.attribution_service import AttributionService
from services.clickhouse_service import ClickHouseDataService
from services.quality_service import QualityService


def get_clickhouse_service() -> ClickHouseDataService:
    """获取 ClickHouse 数据服务实例"""
    return ClickHouseDataService()


def get_quality_service() -> QualityService:
    """获取质量服务实例"""
    return QualityService()


def get_rag_service() -> RAGService:
    """获取 RAG 服务实例"""
    return RAGService()


def get_nl_query_service() -> NLQueryService:
    """获取自然语言查询服务实例"""
    return NLQueryService()


def get_attribution_service() -> AttributionService:
    """获取归因分析服务实例"""
    return AttributionService()


# 类型别名，方便路由使用
ClickHouseServiceDep = Annotated[ClickHouseDataService, Depends(get_clickhouse_service)]
QualityServiceDep = Annotated[QualityService, Depends(get_quality_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
RAGServiceDep = Annotated[RAGService, Depends(get_rag_service)]
NLQueryServiceDep = Annotated[NLQueryService, Depends(get_nl_query_service)]
AttributionServiceDep = Annotated[AttributionService, Depends(get_attribution_service)]
