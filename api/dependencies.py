"""依赖注入"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.engine import Engine

from api.config import Settings, get_settings
from services import ARService, DataService, QualityService


def get_ar_service() -> ARService:
    """获取 AR 服务实例"""
    return ARService()


def get_quality_service() -> QualityService:
    """获取质量服务实例"""
    return QualityService()


def get_data_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DataService:
    """获取数据服务实例"""
    return DataService()


# 类型别名，方便路由使用
ARServiceDep = Annotated[ARService, Depends(get_ar_service)]
QualityServiceDep = Annotated[QualityService, Depends(get_quality_service)]
DataServiceDep = Annotated[DataService, Depends(get_data_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
