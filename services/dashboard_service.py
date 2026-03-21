"""HTML 看版生成服务"""
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from services.clickhouse_service import ClickHouseDataService

PROJECT_ROOT = Path(__file__).parent.parent


class DashboardService:
    """管理看板 HTML 生成"""

    def __init__(self, ch: ClickHouseDataService | None = None):
        self._ch = ch or ClickHouseDataService()
        self._jinja = Environment(
            loader=FileSystemLoader(PROJECT_ROOT / "templates" / "reports"),
            autoescape=True,
        )

    def generate(self, stat_date: date | None = None) -> str:
        """生成看板 HTML 并写入 static/reports/"""
        stat_date = stat_date or date.today()
        date_str = stat_date.isoformat()

        kpi = self._get_kpi(stat_date)
        concentration = self._get_concentration(stat_date)
        distribution = self._get_distribution(stat_date)
        trend = self._get_trend()
        risk_customers = self._get_risk_customers(stat_date)

        template = self._jinja.get_template("dashboard.html.j2")
        html = template.render(
            stat_date=date_str,
            kpi=kpi,
            concentration=concentration,
            distribution=distribution,
            trend=trend,
            risk_customers=risk_customers,
        )

        # 写入文件
        output_dir = PROJECT_ROOT / "static" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"dashboard_{date_str}.html"
        filepath = output_dir / filename
        filepath.write_text(html, encoding="utf-8")

        # 更新 latest 软链接（通过复制实现，跨平台兼容）
        latest_path = output_dir / "dashboard_latest.html"
        latest_path.write_text(html, encoding="utf-8")

        return str(filepath)

    def _get_kpi(self, stat_date: date) -> dict:
        rows = self._ch.execute_query(
            "SELECT "
            "  sum(ar_total) AS ar_total, "
            "  sum(ar_overdue) AS ar_overdue, "
            "  avgIf(ar_overdue / nullIf(ar_total, 0), ar_total > 0) AS overdue_rate, "
            "  count() AS customer_count "
            "FROM dm.dm_customer360 "
            "WHERE stat_date = %(stat_date)s",
            {"stat_date": stat_date.isoformat()},
        )
        if not rows:
            return {"ar_total": 0, "ar_overdue": 0, "overdue_rate": 0, "customer_count": 0}
        r = rows[0]
        return {
            "ar_total": r.get("ar_total") or 0,
            "ar_overdue": r.get("ar_overdue") or 0,
            "overdue_rate": r.get("overdue_rate") or 0,
            "customer_count": r.get("customer_count") or 0,
        }

    def _get_concentration(self, stat_date: date) -> list[dict]:
        rows = self._ch.execute_query(
            "SELECT customer_name, ar_total, ar_overdue "
            "FROM dm.dm_customer360 "
            "WHERE stat_date = %(stat_date)s "
            "ORDER BY ar_total DESC LIMIT 10",
            {"stat_date": stat_date.isoformat()},
        )
        total = sum(r.get("ar_total") or 0 for r in rows)
        return [
            {
                "name": r.get("customer_name", "未知"),
                "amount": r.get("ar_total") or 0,
                "pct": (r.get("ar_total") or 0) / total if total > 0 else 0,
            }
            for r in rows
        ]

    def _get_distribution(self, stat_date: date) -> list[dict]:
        rows = self._ch.execute_query(
            "SELECT "
            "  countIf(ar_overdue = 0) AS bucket_no_overdue, "
            "  countIf(ar_overdue > 0 AND overdue_rate <= 0.3) AS bucket_0_30, "
            "  countIf(overdue_rate > 0.3 AND overdue_rate <= 0.60) AS bucket_30_60, "
            "  countIf(overdue_rate > 0.60) AS bucket_60_plus "
            "FROM dm.dm_customer360 "
            "WHERE stat_date = %(stat_date)s",
            {"stat_date": stat_date.isoformat()},
        )
        if not rows:
            return [
                {"bucket": "无逾期", "count": 0, "pct": 0},
                {"bucket": "0-30天", "count": 0, "pct": 0},
                {"bucket": "30-60天", "count": 0, "pct": 0},
                {"bucket": "60天+", "count": 0, "pct": 0},
            ]
        r = rows[0]
        total = sum(r.get(f"bucket_{k}", 0) or 0 for k in ["no_overdue", "0_30", "30_60", "60_plus"])
        return [
            {"bucket": "无逾期", "count": r.get("bucket_no_overdue") or 0,
             "pct": (r.get("bucket_no_overdue") or 0) / total if total > 0 else 0},
            {"bucket": "0-30天", "count": r.get("bucket_0_30") or 0,
             "pct": (r.get("bucket_0_30") or 0) / total if total > 0 else 0},
            {"bucket": "30-60天", "count": r.get("bucket_30_60") or 0,
             "pct": (r.get("bucket_30_60") or 0) / total if total > 0 else 0},
            {"bucket": "60天+", "count": r.get("bucket_60_plus") or 0,
             "pct": (r.get("bucket_60_plus") or 0) / total if total > 0 else 0},
        ]

    def _get_trend(self) -> list[dict]:
        rows = self._ch.execute_query(
            "SELECT stat_date, "
            "  avgIf(ar_overdue / nullIf(ar_total, 0), ar_total > 0) AS overdue_rate "
            "FROM dm.dm_customer360 "
            "WHERE stat_date >= today() - interval 84 day "
            "GROUP BY stat_date "
            "ORDER BY stat_date"
        )
        return [
            {
                "date": r.get("stat_date"),
                "rate": r.get("overdue_rate") or 0,
            }
            for r in rows
        ]

    def _get_risk_customers(self, stat_date: date) -> list[dict]:
        rows = self._ch.execute_query(
            "SELECT customer_name, ar_total, ar_overdue, overdue_rate, risk_level "
            "FROM dm.dm_customer360 "
            "WHERE stat_date = %(stat_date)s AND overdue_rate > 0.3 "
            "ORDER BY overdue_rate DESC LIMIT 20",
            {"stat_date": stat_date.isoformat()},
        )
        return [
            {
                "name": r.get("customer_name", "未知"),
                "ar_total": r.get("ar_total") or 0,
                "ar_overdue": r.get("ar_overdue") or 0,
                "overdue_rate": r.get("overdue_rate") or 0,
                "risk_level": r.get("risk_level", "中"),
            }
            for r in rows
        ]
