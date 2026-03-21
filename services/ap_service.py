"""AP 数据聚合服务（占位，后续 Task 4 完整实现）"""
from datetime import date
from decimal import Decimal
from typing import Any

from services.clickhouse_service import ClickHouseDataService


class APService:
    """AP 数据查询（不含写入，写入由 APBankStatementParser 处理）"""

    def __init__(self, ch: ClickHouseDataService | None = None):
        self._ch = ch or ClickHouseDataService()

    def get_kpi(self, stat_date: date | None = None) -> dict[str, Any]:
        rows = self._ch.execute_query(
            "SELECT "
            "  sum(amount) AS ap_total, "
            "  sumIf(amount, is_settled = 0) AS unsettled_total, "
            "  sumIf(amount, is_settled = 0 AND due_date < today()) AS overdue_total, "
            "  uniqExact(supplier_name) AS supplier_count "
            "FROM std.ap_std_record"
        )
        if not rows:
            return {
                "ap_total": "0", "unsettled_total": "0",
                "overdue_total": "0", "overdue_rate": 0.0, "supplier_count": 0,
            }
        r = rows[0]
        ap = float(r.get("ap_total") or 0)
        overdue = float(r.get("overdue_total") or 0)
        return {
            "ap_total": str(r.get("ap_total") or 0),
            "unsettled_total": str(r.get("unsettled_total") or 0),
            "overdue_total": str(r.get("overdue_total") or 0),
            "overdue_rate": round(overdue / ap if ap > 0 else 0.0, 4),
            "supplier_count": r.get("supplier_count") or 0,
        }

    def get_suppliers(self, limit: int = 20) -> list[dict]:
        rows = self._ch.execute_query(
            "SELECT "
            "  supplier_name, "
            "  sum(amount) AS total_amount, "
            "  sumIf(amount, is_settled = 0) AS unsettled_amount, "
            "  sumIf(amount, is_settled = 0 AND due_date < today()) AS overdue_amount, "
            "  count() AS record_count "
            "FROM std.ap_std_record "
            "WHERE supplier_name != '' "
            "GROUP BY supplier_name "
            "ORDER BY total_amount DESC "
            f"LIMIT {limit}"
        )
        return [dict(r) for r in rows]

    def get_records(
        self,
        supplier_name: str | None = None,
        is_settled: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        where = ["1=1"]
        if supplier_name:
            where.append(f"supplier_name = '{supplier_name}'")
        if is_settled is not None:
            where.append(f"is_settled = {is_settled}")
        rows = self._ch.execute_query(
            "SELECT * FROM std.ap_std_record "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY bank_date DESC LIMIT {limit}"
        )
        return [dict(r) for r in rows]

    def generate_dashboard(self) -> str:
        """生成 AP HTML 看板（占位，Task 5 完整实现）"""
        from datetime import datetime
        from jinja2 import Environment, FileSystemLoader
        from pathlib import Path

        kpi = self.get_kpi()
        suppliers = self.get_suppliers(limit=10)

        jinja = Environment(
            loader=FileSystemLoader(Path(__file__).parent.parent / "templates" / "reports"),
            autoescape=True,
        )
        template = jinja.get_template("ap_report.html.j2")
        html = template.render(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            kpi=kpi,
            suppliers=suppliers,
        )
        output_dir = Path(__file__).parent.parent / "static" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / "ap_dashboard.html"
        filepath.write_text(html, encoding="utf-8")
        return str(filepath)
