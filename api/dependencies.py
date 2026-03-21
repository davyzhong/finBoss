"""依赖注入"""
from functools import lru_cache

from typing import Annotated

from fastapi import Depends

from api.config import Settings, get_settings
from services.ai import NLQueryService, RAGService
from services.ai.attribution_service import AttributionService
from services.alert_service import AlertService
from services.clickhouse_service import ClickHouseDataService
from services.customer360_service import Customer360Service
from services.quality_service import QualityService
from services.salesperson_mapping_service import SalespersonMappingService
from services.ap_service import APService
from services.field_quality_service import FieldQualityService


@lru_cache
def get_clickhouse_service() -> ClickHouseDataService:
    """获取 ClickHouse 数据服务实例（单例，跨请求复用连接）"""
    return ClickHouseDataService()


@lru_cache
def get_quality_service() -> QualityService:
    """获取质量服务实例（单例）"""
    return QualityService()


@lru_cache
def get_rag_service() -> RAGService:
    """获取 RAG 服务实例（单例）"""
    return RAGService()


@lru_cache
def get_nl_query_service() -> NLQueryService:
    """获取自然语言查询服务实例（单例）"""
    return NLQueryService()


@lru_cache
def get_attribution_service() -> AttributionService:
    """获取归因分析服务实例（单例）"""
    return AttributionService()


@lru_cache
def get_customer360_service() -> Customer360Service:
    """获取客户360服务实例（单例）"""
    return Customer360Service()


@lru_cache
def get_alert_service() -> AlertService:
    """获取预警服务实例（单例）"""
    return AlertService()


@lru_cache
def get_salesperson_mapping_service() -> SalespersonMappingService:
    """获取业务员映射服务实例（单例）"""
    return SalespersonMappingService()


@lru_cache
def get_ap_service() -> APService:
    """获取 AP 服务实例（单例）"""
    return APService()


@lru_cache
def get_field_quality_service() -> FieldQualityService:
    """获取字段质量服务实例（单例）"""
    return FieldQualityService()


# 类型别名，方便路由使用
ClickHouseServiceDep = Annotated[ClickHouseDataService, Depends(get_clickhouse_service)]
QualityServiceDep = Annotated[QualityService, Depends(get_quality_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
RAGServiceDep = Annotated[RAGService, Depends(get_rag_service)]
NLQueryServiceDep = Annotated[NLQueryService, Depends(get_nl_query_service)]
AttributionServiceDep = Annotated[AttributionService, Depends(get_attribution_service)]
Customer360ServiceDep = Annotated[Customer360Service, Depends(get_customer360_service)]
AlertServiceDep = Annotated[AlertService, Depends(get_alert_service)]
SalespersonMappingServiceDep = Annotated[SalespersonMappingService, Depends(get_salesperson_mapping_service)]
APServiceDep = Annotated[APService, Depends(get_ap_service)]
FieldQualityServiceDep = Annotated[FieldQualityService, Depends(get_field_quality_service)]
