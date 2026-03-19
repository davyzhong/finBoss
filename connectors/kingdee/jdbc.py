# connectors/kingdee/jdbc.py
"""金蝶 MSSQL 数据库连接"""
from typing import Any, Iterator

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from connectors.common.base import BaseConnector


class KingdeeJDBC(BaseConnector):
    """金蝶 MSSQL JDBC 连接器"""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)

    @property
    def connection_url(self) -> str:
        cfg = self.config
        return (
            f"mssql+pymssql://{cfg['user']}:{cfg['password']}"
            f"@{cfg['host']}:{cfg['port']}/{cfg['database']}"
        )

    def connect(self) -> None:
        self._engine = create_engine(
            self.connection_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        self._connected = True

    def disconnect(self) -> None:
        if self._engine:
            self._engine.dispose()
            self._engine = None
        self._connected = False

    def test_connection(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def fetch(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        batch_size: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        for chunk in pd.read_sql(
            text(query), self._engine, params=params or {}, chunksize=batch_size
        ):
            for _, row in chunk.iterrows():
                yield row.to_dict()
