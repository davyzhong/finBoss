# services/data_service.py
"""数据查询服务"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from api.config import get_settings


class DataService:
    """数据查询服务 - Doris/ClickHouse 查询封装"""

    def __init__(self, engine: Optional[Engine] = None):
        settings = get_settings()
        if engine is None:
            self.engine = create_engine(
                settings.doris.connection_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
        else:
            self.engine = engine

    def execute_query(
        self,
        sql: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """执行查询并返回字典列表

        Args:
            sql: SQL 语句
            params: 查询参数

        Returns:
            查询结果列表
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]

    def execute_scalar(self, sql: str) -> Any:
        """执行查询并返回标量值

        Args:
            sql: SQL 语句

        Returns:
            查询结果（单个值）
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(sql))
            return result.scalar()

    def get_ar_summary(
        self,
        company_code: Optional[str] = None,
        stat_date: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """获取 AR 汇总数据

        Args:
            company_code: 公司编码（可选）
            stat_date: 统计日期（可选）

        Returns:
            AR 汇总数据列表
        """
        sql = """
            SELECT
                stat_date,
                company_code,
                company_name,
                total_ar_amount,
                received_amount,
                allocated_amount,
                unallocated_amount,
                overdue_amount,
                overdue_count,
                total_count,
                overdue_rate,
                aging_0_30,
                aging_31_60,
                aging_61_90,
                aging_91_180,
                aging_180_plus,
                etl_time
            FROM dm.dm_ar_summary
            WHERE 1=1
        """
        params = {}
        if company_code:
            sql += " AND company_code = :company_code"
            params["company_code"] = company_code
        if stat_date:
            sql += " AND stat_date = :stat_date"
            params["stat_date"] = stat_date
        sql += " ORDER BY stat_date DESC, company_code LIMIT 1000"
        return self.execute_query(sql, params)

    def get_customer_ar(
        self,
        customer_code: Optional[str] = None,
        is_overdue: Optional[bool] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """获取客户 AR 明细

        Args:
            customer_code: 客户编码（可选）
            is_overdue: 是否逾期（可选）
            limit: 返回条数限制

        Returns:
            客户 AR 数据列表
        """
        sql = """
            SELECT
                stat_date,
                customer_code,
                customer_name,
                company_code,
                total_ar_amount,
                overdue_amount,
                overdue_count,
                total_count,
                overdue_rate,
                last_bill_date,
                etl_time
            FROM dm.dm_customer_ar
            WHERE 1=1
        """
        params: dict[str, Any] = {}
        if customer_code:
            sql += " AND customer_code = :customer_code"
            params["customer_code"] = customer_code
        if is_overdue is not None:
            sql += " AND overdue_count > 0" if is_overdue else " AND overdue_count = 0"
        # LIMIT 在 MySQL/Doris 中不支持绑定参数，直接拼接（limit 已由 FastAPI 校验为 int）
        sql += f" ORDER BY overdue_amount DESC LIMIT {int(limit)}"
        return self.execute_query(sql, params)

    def get_latest_etl_time(self, table_name: str) -> datetime:
        """获取表的最新 ETL 时间

        Args:
            table_name: 表名（如 'std.std_ar'）

        Returns:
            最新 ETL 时间
        """
        sql = f"SELECT MAX(etl_time) as latest_etl_time FROM {table_name}"
        result = self.execute_query(sql)
        if not result:
            return datetime.now()
        latest = result[0].get("latest_etl_time")
        if latest is None:
            return datetime.now()
        return latest
        self,
        bill_no: Optional[str] = None,
        customer_code: Optional[str] = None,
        company_code: Optional[str] = None,
        is_overdue: Optional[bool] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """获取 AR 应收明细

        Args:
            bill_no: 应收单号（可选）
            customer_code: 客户编码（可选）
            company_code: 公司编码（可选）
            is_overdue: 是否逾期（可选）
            limit: 返回条数限制

        Returns:
            AR 明细数据列表
        """
        sql = """
            SELECT
                id,
                stat_date,
                company_code,
                company_name,
                customer_code,
                customer_name,
                bill_no,
                bill_date,
                due_date,
                bill_amount,
                received_amount,
                allocated_amount,
                unallocated_amount,
                aging_bucket,
                aging_days,
                is_overdue,
                overdue_days,
                status,
                etl_time
            FROM std.std_ar
            WHERE 1=1
        """
        params: dict[str, Any] = {}
        if bill_no:
            sql += " AND bill_no = :bill_no"
            params["bill_no"] = bill_no
        if customer_code:
            sql += " AND customer_code = :customer_code"
            params["customer_code"] = customer_code
        if company_code:
            sql += " AND company_code = :company_code"
            params["company_code"] = company_code
        if is_overdue is not None:
            sql += " AND is_overdue = :is_overdue"
            params["is_overdue"] = is_overdue
        # LIMIT 在 MySQL/Doris 中不支持绑定参数，直接拼接（limit 已由 FastAPI 校验为 int）
        sql += f" ORDER BY bill_date DESC LIMIT {int(limit)}"
        return self.execute_query(sql, params)
