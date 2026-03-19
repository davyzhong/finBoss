"""数据源连接器基类"""
from abc import ABC, abstractmethod
from typing import Any, Iterator


class BaseConnector(ABC):
    """数据源连接器抽象基类"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._connected = False

    @abstractmethod
    def connect(self) -> None:
        """建立连接"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """测试连接是否正常"""
        pass

    @abstractmethod
    def fetch(self, query: str, batch_size: int = 1000) -> Iterator[dict[str, Any]]:
        """批量获取数据"""
        pass

    def __enter__(self) -> "BaseConnector":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
