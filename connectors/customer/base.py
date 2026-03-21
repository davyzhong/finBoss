# connectors/customer/base.py
"""ERP 客户连接器抽象接口"""
from abc import ABC, abstractmethod
from datetime import date
import logging

from schemas.customer360 import RawCustomer, RawARRecord

logger = logging.getLogger(__name__)


class ERPCustomerConnector(ABC):
    """ERP 客户数据连接器抽象接口

    所有 ERP 客户数据连接器必须实现此接口。
    Phase 4B 先实现 KingdeeCustomerConnector，
    未来接入其他 ERP 时新增实现类即可。
    """

    @property
    @abstractmethod
    def source_system(self) -> str:
        """ERP 来源标识，如 'kingdee', 'yonyou', 'sap'"""

    @abstractmethod
    def fetch_customers(self) -> list[RawCustomer]:
        """从 ERP 获取客户主数据"""

    @abstractmethod
    def fetch_ar_records(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawARRecord]:
        """从 ERP 获取应收明细（用于客户账龄分析）"""


class ERPCustomerConnectorRegistry:
    """ERP 连接器注册表（支持多 ERP）"""

    _connectors: dict[str, type[ERPCustomerConnector]] = {}

    @classmethod
    def register(cls, source_system: str, connector_cls: type[ERPCustomerConnector]) -> None:
        if not issubclass(connector_cls, ERPCustomerConnector):
            raise TypeError(f"{connector_cls} must inherit from ERPCustomerConnector")
        cls._connectors[source_system] = connector_cls

    @classmethod
    def get(cls, source_system: str) -> ERPCustomerConnector:
        if source_system not in cls._connectors:
            raise ValueError(f"未注册的 ERP: {source_system}")
        return cls._connectors[source_system]()

    @classmethod
    def fetch_all_customers(cls) -> list[RawCustomer]:
        """从所有已注册的 ERP 获取客户数据"""
        results: list[RawCustomer] = []
        for source, connector_cls in cls._connectors.items():
            try:
                connector = connector_cls()
                results.extend(connector.fetch_customers())
            except Exception as e:
                logger.warning(f"ERP {source} 拉取失败: {e}")
        return results

    @classmethod
    def fetch_all_ar_records(
        cls,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawARRecord]:
        """从所有已注册的 ERP 获取应收数据"""
        results: list[RawARRecord] = []
        for source, connector_cls in cls._connectors.items():
            try:
                connector = connector_cls()
                results.extend(connector.fetch_ar_records(start_date=start_date, end_date=end_date))
            except Exception as e:
                logger.warning(f"ERP {source} 应收拉取失败: {e}")
        return results
