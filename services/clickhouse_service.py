"""ClickHouse 数据查询服务"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from clickhouse_driver import Client
from schemas.customer360 import (
    Customer360Record,
    Customer360Summary,
    CustomerDistribution,
    CustomerMergeQueue,
    CustomerTrend,
    MatchAction,
    MatchResult,
    RawCustomer,
)

_ALLOWED_TABLE_PREFIXES = ("raw.", "std.", "dm.")
_LIMIT_MAX = 10000


def _validate_limit(value: int | None) -> int:
    """Validate limit as a positive integer within allowed range."""
    if value is None:
        return 100
    if not isinstance(value, int) or value <= 0 or value > _LIMIT_MAX:
        raise ValueError(f"limit must be a positive integer <= {_LIMIT_MAX}")
    return value


def _validate_table_name(name: str) -> str:
    """Validate table_name against an allowlist of known prefixes."""
    if not isinstance(name, str):
        raise ValueError("table_name must be a string")
    lower = name.lower()
    if not any(lower.startswith(prefix.lower()) for prefix in _ALLOWED_TABLE_PREFIXES):
        raise ValueError(
            f"table_name must start with one of: {', '.join(_ALLOWED_TABLE_PREFIXES)}"
        )
    return name

from api.config import get_settings


class ClickHouseDataService:
    """ClickHouse 数据查询服务"""

    def __init__(self, client: Client | None = None):
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
        params: dict[str, Any] | None = None,
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

    def execute(self, sql: str) -> None:
        """执行 DDL 等无返回值的语句

        Args:
            sql: DDL 或其他无返回值要求的 SQL 语句
        """
        self.client.execute(sql)

    def get_ar_summary(
        self,
        company_code: str | None = None,
        stat_date: str | None = None,
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
        customer_code: str | None = None,
        is_overdue: bool | None = None,
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
        validated_limit = _validate_limit(limit)
        sql += f" ORDER BY overdue_amount DESC LIMIT {validated_limit}"
        return self.execute_query(sql, params)

    def get_latest_etl_time(self, table_name: str) -> datetime:
        """获取表的最新 ETL 时间

        Args:
            table_name: 表名（如 'std.std_ar'）

        Returns:
            最新 ETL 时间
        """
        validated_table = _validate_table_name(table_name)
        sql = f"SELECT MAX(etl_time) as latest_etl_time FROM {validated_table}"
        result = self.execute_query(sql)
        if not result:
            return datetime.now()
        latest = result[0].get("latest_etl_time")
        if latest is None:
            return datetime.now()
        return latest

    def get_ar_detail(
        self,
        bill_no: str | None = None,
        customer_code: str | None = None,
        company_code: str | None = None,
        is_overdue: bool | None = None,
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
        validated_limit = _validate_limit(limit)
        sql += f" ORDER BY bill_date DESC LIMIT {validated_limit}"
        return self.execute_query(sql, params)

    # --- 客户360相关方法（Phase 4B） ---

    def insert_customer360(self, records: list[Customer360Record]) -> int:
        """批量写入客户360记录"""
        if not records:
            return 0
        sql = """
        INSERT INTO dm.dm_customer360 (
            unified_customer_code, raw_customer_ids, source_systems,
            customer_name, customer_short_name,
            ar_total, ar_overdue, overdue_rate, payment_score,
            risk_level, merge_status,
            last_payment_date, first_coop_date, company_code,
            stat_date, updated_at
        ) VALUES
        """
        values = [
            (
                r.unified_customer_code,
                r.raw_customer_ids,
                r.source_systems,
                r.customer_name,
                r.customer_short_name or "",
                float(r.ar_total),
                float(r.ar_overdue),
                r.overdue_rate,
                r.payment_score,
                r.risk_level,
                r.merge_status,
                r.last_payment_date,
                r.first_coop_date,
                r.company_code or "",
                r.stat_date,
                r.updated_at,
            )
            for r in records
        ]
        self.client.execute(sql, values)
        return len(records)

    def insert_merge_queue(self, items: list[CustomerMergeQueue]) -> int:
        """写入合并复核队列"""
        if not items:
            return 0
        sql = """
        INSERT INTO dm.customer_merge_queue (
            id, action, similarity, reason,
            customer_ids, customer_names, unified_customer_code,
            status, operator, operated_at, undo_record_id, created_at
        ) VALUES
        """
        values = [
            (
                item.id,
                item.match_result.action.value,
                item.match_result.similarity,
                item.match_result.reason,
                [c.customer_id for c in item.match_result.customers],
                [c.customer_name for c in item.match_result.customers],
                item.match_result.unified_customer_code or "",
                item.status,
                item.operator or "",
                item.operated_at,
                item.undo_record_id or "",
                item.match_result.created_at,
            )
            for item in items
        ]
        self.client.execute(sql, values)
        return len(items)

    def get_customer360_summary(self, stat_date: date) -> Customer360Summary:
        """管理层汇总"""
        sql = """
        SELECT
            uniqExact(unified_customer_code)                           AS total_customers,
            sum(merge_status IN ('auto_merged', 'confirmed'))          AS merged_customers,
            sum(merge_status = 'pending')                              AS pending_merges,
            sum(ar_total)                                             AS ar_total,
            sum(ar_overdue)                                           AS ar_overdue_total,
            sum(ar_overdue) / sum(ar_total)                           AS overall_overdue_rate,
            sum(risk_level = '高')                                     AS risk_high,
            sum(risk_level = '中')                                     AS risk_mid,
            sum(risk_level = '低')                                     AS risk_low
        FROM dm.dm_customer360
        WHERE stat_date = %(stat_date)s
        """
        rows = self.execute_query(sql, {"stat_date": stat_date})
        if not rows:
            # Return zero'd summary for dates with no data
            return Customer360Summary(
                total_customers=0,
                merged_customers=0,
                pending_merges=0,
                ar_total=Decimal("0"),
                ar_overdue_total=Decimal("0"),
                overall_overdue_rate=0.0,
                risk_distribution={"高": 0, "中": 0, "低": 0},
                concentration_top10_ratio=0.0,
            )
        row = rows[0]

        # 计算前10客户集中度（子查询）
        top10_sql = """
        SELECT sum(ar_total) AS top10_ar
        FROM (
            SELECT ar_total FROM dm.dm_customer360
            WHERE stat_date = %(stat_date)s
            ORDER BY ar_total DESC LIMIT 10
        )
        """
        top10_row = self.execute_query(top10_sql, {"stat_date": stat_date})[0]
        total_ar = float(row["ar_total"]) if row["ar_total"] else 0.0
        top10_ar = float(top10_row["top10_ar"]) if top10_row and top10_row["top10_ar"] else 0.0
        concentration = (top10_ar / total_ar) if total_ar > 0 else 0.0

        raw_rate = row["overall_overdue_rate"]
        overall_overdue_rate = float(raw_rate) if raw_rate is not None else 0.0
        if overall_overdue_rate == float("inf") or overall_overdue_rate != overall_overdue_rate:
            overall_overdue_rate = 0.0
        overall_overdue_rate *= 100

        if concentration == float("inf") or concentration != concentration:
            concentration = 0.0

        return Customer360Summary(
            total_customers=row["total_customers"],
            merged_customers=row["merged_customers"],
            pending_merges=row["pending_merges"],
            ar_total=Decimal(str(row["ar_total"])),
            ar_overdue_total=Decimal(str(row["ar_overdue_total"])),
            overall_overdue_rate=overall_overdue_rate,  # already in percentage
            risk_distribution={"高": row["risk_high"], "中": row["risk_mid"], "低": row["risk_low"]},
            concentration_top10_ratio=concentration,
        )

    def get_customer360_distribution(self, stat_date: date) -> CustomerDistribution:
        """客户分布"""
        by_company_sql = """
        SELECT company_code AS company, count() AS count, sum(ar_total) AS ar_total
        FROM dm.dm_customer360 t
        WHERE stat_date = %(stat_date)s
        GROUP BY company_code ORDER BY ar_total DESC LIMIT 20
        """
        by_risk_sql = """
        SELECT risk_level AS risk, count() AS count, sum(ar_total) AS ar_total
        FROM dm.dm_customer360
        WHERE stat_date = %(stat_date)s
        GROUP BY risk_level
        """
        by_company = [dict(row) for row in self.execute_query(by_company_sql, {"stat_date": stat_date})]
        by_risk = [dict(row) for row in self.execute_query(by_risk_sql, {"stat_date": stat_date})]
        return CustomerDistribution(
            by_company=by_company,
            by_risk_level=by_risk,
            by_overdue_bucket=[{"bucket": "0-30天", "count": 0, "amount": 0.0}],
        )

    def get_customer360_trend(self, months: int = 12) -> CustomerTrend:
        """客户/应收趋势"""
        sql = """
        SELECT
            toYYYYMM(stat_date) AS ym,
            uniqExact(unified_customer_code) AS customer_count,
            sum(ar_total) AS ar_total,
            sum(ar_overdue) / sum(ar_total) AS overdue_rate
        FROM dm.dm_customer360
        WHERE stat_date >= today() - INTERVAL %(months)s MONTH
        GROUP BY ym
        ORDER BY ym
        """
        rows = self.execute_query(sql, {"months": months})
        return CustomerTrend(
            dates=[str(r["ym"]) for r in rows],
            customer_counts=[r["customer_count"] for r in rows],
            ar_totals=[float(r["ar_total"]) for r in rows],
            overdue_rates=[float(r["overdue_rate"]) for r in rows],
        )

    def get_customer360_detail(self, unified_code: str) -> dict[str, Any]:
        """客户详情（包含账龄分布和最近应收单）"""
        sql = """
        SELECT * FROM dm.dm_customer360
        WHERE unified_customer_code = %(code)s
        ORDER BY stat_date DESC LIMIT 1
        """
        rows = self.execute_query(sql, {"code": unified_code})
        if not rows:
            return {}
        return dict(rows[0])

    def get_merge_queue(self, status: str = "pending") -> list[CustomerMergeQueue]:
        """获取合并队列"""
        sql = """
        SELECT * FROM dm.customer_merge_queue
        WHERE status = %(status)s
        ORDER BY created_at DESC
        """
        rows = self.execute_query(sql, {"status": status})
        return [self._row_to_merge_queue(r) for r in rows]

    def _row_to_merge_queue(self, row: dict) -> CustomerMergeQueue:
        """将数据库行反序列化为 CustomerMergeQueue"""
        customer_ids: list[str] = row.get("customer_ids") or []
        customer_names: list[str] = row.get("customer_names") or []
        source_systems: list[str] = row.get("source_systems") or []
        customers = [
            RawCustomer(
                source_system=source_systems[i] if i < len(source_systems) else "kingdee",
                customer_id=customer_ids[i],
                customer_name=customer_names[i] if i < len(customer_names) else "",
            )
            for i in range(len(customer_ids))
        ]
        match = MatchResult(
            action=MatchAction(row["action"]),
            customers=customers,
            unified_customer_code=row["unified_customer_code"] or None,
            similarity=row["similarity"],
            reason=row["reason"],
        )
        return CustomerMergeQueue(
            id=row["id"],
            match_result=match,
            status=row["status"],
            operator=row["operator"] or None,
            operated_at=row["operated_at"],
            undo_record_id=row["undo_record_id"] or None,
        )

    def confirm_merge(self, queue_id: str, operator: str) -> dict[str, Any]:
        """确认合并：更新队列状态 + 更新 dm_customer360"""
        queue_row = self.execute_query(
            "SELECT unified_customer_code FROM dm.customer_merge_queue WHERE id = %(id)s",
            {"id": queue_id},
        )
        if not queue_row:
            return {"id": queue_id, "status": "not_found"}
        unified_code = queue_row[0]["unified_customer_code"]

        self.client.execute(
            "UPDATE dm.customer_merge_queue SET status = 'confirmed', operator = %(op)s, operated_at = now() WHERE id = %(id)s",
            {"op": operator, "id": queue_id},
        )
        today = date.today()
        if unified_code:
            self.client.execute(
                "ALTER TABLE dm.dm_customer360 UPDATE merge_status = 'confirmed', updated_at = now() "
                "WHERE unified_customer_code = %(code)s AND stat_date = %(d)s AND merge_status = 'auto_merged'",
                {"code": unified_code, "d": today},
            )
        return {"id": queue_id, "status": "confirmed", "unified_customer_code": unified_code, "operator": operator}

    def reject_merge(self, queue_id: str, operator: str) -> dict[str, Any]:
        """拒绝合并"""
        self.client.execute(
            "UPDATE dm.customer_merge_queue SET status = 'rejected', operator = %(op)s, operated_at = now() WHERE id = %(id)s",
            {"op": operator, "id": queue_id},
        )
        return {"id": queue_id, "status": "rejected", "operator": operator}

    def undo_merge(
        self,
        unified_customer_code: str,
        original_customer_id: str,
        operator: str,
        reason: str,
    ) -> dict[str, Any]:
        """撤销合并"""
        import uuid

        # Step 1: Read the current raw_customer_ids array for the unified customer
        rows = self.execute_query(
            "SELECT raw_customer_ids FROM dm.dm_customer360 "
            "WHERE unified_customer_code = %(code)s ORDER BY updated_at DESC LIMIT 1",
            {"code": unified_customer_code},
        )

        if rows:
            current_ids = rows[0]["raw_customer_ids"]  # Array(String) -> Python list
            # Step 2: Filter out original_customer_id
            new_ids = [cid for cid in current_ids if cid != original_customer_id]
            # Step 3: UPDATE the row with the new array
            self.client.execute(
                "ALTER TABLE dm.dm_customer360 UPDATE raw_customer_ids = %(new_ids)s "
                "WHERE unified_customer_code = %(code)s",
                {"new_ids": new_ids, "code": unified_customer_code},
            )

        # Step 4: Insert history record
        undo_id = str(uuid.uuid4())
        self.client.execute(
            "INSERT INTO dm.merge_history (id, unified_customer_code, source_system, original_customer_id, operated_at, operator, undo_record_id) VALUES",
            [(undo_id, unified_customer_code, "kingdee", original_customer_id, datetime.now(), operator, "")],
        )
        return {"undo_id": undo_id, "unified_customer_code": unified_customer_code}

    def get_customer_attribution(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """AI 归因数据（含期初/期末对比 delta）"""
        curr_sql = """
        SELECT
            unified_customer_code AS customer_code,
            customer_name,
            ar_overdue AS ar_overdue_curr,
            overdue_rate AS overdue_rate_curr,
            risk_level
        FROM dm.dm_customer360
        WHERE stat_date = %(end_date)s
        ORDER BY ar_overdue DESC
        LIMIT 200
        """
        curr_rows = self.execute_query(curr_sql, {"end_date": end_date})
        if not curr_rows:
            return {"dimension": "customer", "data": []}

        prev_sql = """
        SELECT
            unified_customer_code AS customer_code,
            ar_overdue AS ar_overdue_prev,
            overdue_rate AS overdue_rate_prev
        FROM dm.dm_customer360
        WHERE stat_date = %(start_date)s
        """
        prev_map = {r["customer_code"]: r for r in self.execute_query(prev_sql, {"start_date": start_date})}

        data = []
        for row in curr_rows:
            code = row["customer_code"]
            prev = prev_map.get(code, {})
            ar_prev = float(prev.get("ar_overdue_prev") or 0.0)
            rate_prev = float(prev.get("overdue_rate_prev") or 0.0)
            ar_curr = float(row["ar_overdue_curr"])
            rate_curr = float(row["overdue_rate_curr"])
            data.append({
                "customer_code": code,
                "customer_name": row["customer_name"],
                "ar_overdue_curr": ar_curr,
                "ar_overdue_prev": ar_prev,
                "overdue_delta": ar_curr - ar_prev,
                "overdue_rate_curr": rate_curr,
                "overdue_rate_prev": rate_prev,
                "risk_level": row["risk_level"],
            })
        data.sort(key=lambda x: x["overdue_delta"], reverse=True)
        return {"dimension": "customer", "data": data}

