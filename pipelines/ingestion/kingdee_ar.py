# pipelines/ingestion/kingdee_ar.py
"""金蝶 AR 数据接入管道"""
import logging
from datetime import datetime, timedelta
from typing import Any, Iterator

from connectors.kingdee.jdbc import KingdeeJDBC
from connectors.kingdee.models import KingdeeARVerify

logger = logging.getLogger(__name__)


class KingdeeARIngester:
    """金蝶 AR 数据接入器"""

    def __init__(self, db_config: dict[str, Any]):
        self.connector = KingdeeJDBC(db_config)

    def ingest_full(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Iterator[KingdeeARVerify]:
        """全量接入 AR 数据"""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=90)
        if end_date is None:
            end_date = datetime.now()

        query = f"""
            SELECT * FROM t_ar_verify
            WHERE FDATE >= '{start_date.strftime('%Y-%m-%d')}'
              AND FDATE <= '{end_date.strftime('%Y-%m-%d')}'
            ORDER BY FDATE DESC
        """
        logger.info(f"Ingesting AR data from {start_date} to {end_date}")
        with self.connector:
            for row in self.connector.fetch(query):
                yield KingdeeARVerify(**row)

    def ingest_incremental(
        self,
        last_sync_time: datetime,
    ) -> Iterator[KingdeeARVerify]:
        """增量接入 AR 数据"""
        query = f"""
            SELECT * FROM t_ar_verify
            WHERE FMODIFYDATE >= '{last_sync_time.strftime('%Y-%m-%d %H:%M:%S')}'
            ORDER BY FMODIFYDATE ASC
        """
        logger.info(f"Incremental AR data since {last_sync_time}")
        with self.connector:
            for row in self.connector.fetch(query):
                yield KingdeeARVerify(**row)
