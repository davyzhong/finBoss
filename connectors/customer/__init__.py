# connectors/customer/__init__.py
"""ERP 客户连接器"""
from connectors.customer.base import (
    ERPCustomerConnector,
    ERPCustomerConnectorRegistry,
    RawCustomer,
    RawARRecord,
)
from connectors.customer.kingdee import KingdeeCustomerConnector

# 注册默认连接器
ERPCustomerConnectorRegistry.register("kingdee", KingdeeCustomerConnector)

__all__ = [
    "ERPCustomerConnector",
    "ERPCustomerConnectorRegistry",
    "RawCustomer",
    "RawARRecord",
    "KingdeeCustomerConnector",
]
