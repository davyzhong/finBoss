# connectors/customer/kingdee.py
"""金蝶客户连接器"""
import logging
from datetime import date
from typing import Any

import pymssql

from api.config import KingdeeDBConfig, get_settings
from connectors.customer.base import ERPCustomerConnector
from schemas.customer360 import RawCustomer, RawARRecord

logger = logging.getLogger(__name__)


class KingdeeCustomerConnector(ERPCustomerConnector):
    """金蝶客户连接器

    客户主数据从金蝶 MSSQL 数据库直接查询。
    应收明细复用 pipelines.ingestion.kingdee_ar.KingdeeARIngester。
    """

    def __init__(self, db_config: KingdeeDBConfig | None = None):
        self._config = db_config or get_settings().kingdee

    @property
    def source_system(self) -> str:
        return "kingdee"

    def _execute(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """执行 SQL 查询，返回字典列表"""
        conn = pymssql.connect(
            server=self._config.host,
            port=self._config.port,
            user=self._config.user,
            password=self._config.password,
            database=self._config.name,
        )
        try:
            with conn.cursor(as_dict=True) as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        finally:
            conn.close()

    def fetch_customers(self) -> list[RawCustomer]:
        """从金蝶客户主数据表获取客户信息

        表名说明：
        - **需实施团队确认**：金蝶 ERP 的客户主数据表名（常见如 t_bd_customer、t_pm_branch 等不同版本表名不同）。
        - Phase 4B 实现前，团队需在金蝶管理后台确认实际表名及字段映射。
        - 此处 SQL 为占位符，标注了需要替换的位置。
        """
        # TODO(实施): 替换为实际客户主数据表名
        customer_table = "t_bd_customer"  # ← 待确认
        sql = f"""
        SELECT
            fitem3001 AS customer_id,
            fitem3002 AS customer_name,
            fitem3003 AS customer_short_name,
            fitem3004 AS address,
            fitem3005 AS contact,
            fitem3006 AS phone
        FROM {customer_table}
        WHERE fitem3001 IS NOT NULL
        """
        rows = self._execute(sql)
        return [
            RawCustomer(
                source_system=self.source_system,
                customer_id=str(row["customer_id"]),
                customer_name=row["customer_name"] or "",
                customer_short_name=row.get("customer_short_name"),
                address=row.get("address"),
                contact=row.get("contact"),
                phone=row.get("phone"),
            )
            for row in rows
        ]

    def fetch_ar_records(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawARRecord]:
        """从金蝶应收单表获取应收明细

        复用 pipelines.ingestion.kingdee_ar.KingdeeARIngester。
        """
        from pipelines.ingestion.kingdee_ar import KingdeeARIngester

        db_dict: dict[str, Any] = {
            "host": self._config.host,
            "port": self._config.port,
            "database": self._config.name,
            "user": self._config.user,
            "password": self._config.password,
        }
        ingester = KingdeeARIngester(db_dict)
        raw_records = list(ingester.ingest_full(start_date=start_date, end_date=end_date))
        return [
            RawARRecord(
                source_system=self.source_system,
                customer_id=str(r.fcustid),
                customer_name=r.fcustname or "",
                bill_no=r.fbillno,
                bill_date=r.fdate.date() if hasattr(r.fdate, "date") else r.fdate,
                due_date=r.fdate.date() if hasattr(r.fdate, "date") else r.fdate,
                bill_amount=r.fbillamount,
                received_amount=r.fpaymentamount,
                is_overdue=(r.funallocateamount > 0),
                overdue_days=0,
                company_code=str(r.fcompanyid),
            )
            for r in raw_records
        ]
