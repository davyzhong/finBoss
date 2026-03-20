"""ClickHouse 数据查询服务"""
from datetime import datetime
from typing import Any, Optional

from clickhouse_driver import Client

from api.config import get_settings


class ClickHouseDataService:
    """ClickHouse 数据查询服务"""

    def __init__(self, client: Optional[Client] = None):
        settings = get_settings()
        if client is None:
            self.client = Client(
                host=settings.clickhouse.host,
                port=settings.clickhouse.port,
                user=settings.clickhouse.user,
                password=settings.clickhouse.password,
                database=settings.clickhouse.database,
            )
        else:
            self.client = client

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
        # 使用 with_column_types=True 获取列信息
        # clickhouse-driver 返回 (data, column_types) 元组
        result = self.client.execute(sql, params or {}, with_column_types=True)
        if not result or not result[0]:
            return []

        data, column_types = result
        # column_types 是 [(列名, 类型), ...] 格式
        column_names = [col[0] for col in column_types]
        return [dict(zip(column_names, row)) for row in data]

    def execute_scalar(self, sql: str) -> Any:
        """执行查询并返回标量值

        Args:
            sql: SQL 语句

        Returns:
            查询结果（单个值）
        """
        result = self.client.execute(sql)
        if not result:
            return None
        return result[0][0] if result else None

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
            sql += " AND company_code = %(company_code)s"
            params["company_code"] = company_code
        if stat_date:
            sql += " AND stat_date = %(stat_date)s"
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
            sql += " AND customer_code = %(customer_code)s"
            params["customer_code"] = customer_code
        if is_overdue is not None:
            sql += " AND overdue_count > 0" if is_overdue else " AND overdue_count = 0"
        # ClickHouse 直接拼接 limit
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

    def get_ar_detail(
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
            sql += " AND bill_no = %(bill_no)s"
            params["bill_no"] = bill_no
        if customer_code:
            sql += " AND customer_code = %(customer_code)s"
            params["customer_code"] = customer_code
        if company_code:
            sql += " AND company_code = %(company_code)s"
            params["company_code"] = company_code
        if is_overdue is not None:
            sql += " AND is_overdue = %(is_overdue)s"
            params["is_overdue"] = is_overdue
        # ClickHouse 直接拼接 limit
        sql += f" ORDER BY bill_date DESC LIMIT {int(limit)}"
        return self.execute_query(sql, params)
