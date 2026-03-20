"""依赖注入"""
from typing import Annotated

from fastapi import Depends

from api.config import Settings, get_settings
from services.clickhouse_service import ClickHouseDataService
from services.quality_service import QualityService


def get_clickhouse_service() -> ClickHouseDataService:
    """获取 ClickHouse 数据服务实例"""
    return ClickHouseDataService()


def get_quality_service() -> QualityService:
    """获取质量服务实例"""
    return QualityService()


# 类型别名，方便路由使用
ClickHouseServiceDep = Annotated[ClickHouseDataService, Depends(get_clickhouse_service)]
QualityServiceDep = Annotated[QualityService, Depends(get_quality_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
