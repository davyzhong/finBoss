"""自动化报告服务"""
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from services.clickhouse_service import ClickHouseDataService

PROJECT_ROOT = Path(__file__).parent.parent


class ReportService:
    """报告生成与发送"""

    def __init__(self, ch: ClickHouseDataService | None = None):
        self._ch = ch or ClickHouseDataService()
        self._jinja = Environment(
            loader=FileSystemLoader(PROJECT_ROOT / "templates" / "reports"),
            autoescape=True,
        )

    def generate(self, report_type: str) -> str:
        """生成报告 HTML"""
        today = date.today()
        if report_type == "weekly":
            period_start = today - timedelta(days=today.weekday() + 7)
            period_end = period_start + timedelta(days=6)
            template_name = "weekly_report.html.j2"
        else:  # monthly
            period_start = today.replace(day=1) - timedelta(days=1)
            period_start = period_start.replace(day=1)
            period_end = today.replace(day=1) - timedelta(days=1)
            template_name = "monthly_report.html.j2"

        # 获取概览数据
        overview = self._get_overview()
        # 获取环比
        mom = self._get_mom_change()
        # 获取风险客户
        risk_customers = self._get_risk_customers()
        # 获取集中度
        concentration = self._get_concentration()

        template_ctx = dict(
            report_type=report_type,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            overview=overview,
            mom=mom,
            risk_customers=risk_customers,
            concentration=concentration,
        )

        # 月报额外增加同比
        if report_type == "monthly":
            template_ctx["yoy"] = self._get_yoy_change()

        template = self._jinja.get_template(template_name)
        html = template.render(**template_ctx)

        output_dir = PROJECT_ROOT / "static" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{report_type}_{today.isoformat()}.html"
        filepath = output_dir / filename
        filepath.write_text(html, encoding="utf-8")

        # 记录
        self._save_record(report_type, period_start, period_end, str(filepath))

        return str(filepath)

    def _get_overview(self) -> dict:
        rows = self._ch.execute_query(
            "SELECT "
            "  sum(ar_total) AS ar_total, "
            "  sum(ar_overdue) AS ar_overdue, "
            "  avgIf(ar_overdue / nullIf(ar_total, 0), ar_total > 0) AS overdue_rate, "
            "  count() AS total_customers "
            "FROM dm.dm_customer360 "
            "WHERE stat_date = (SELECT max(stat_date) FROM dm.dm_customer360)"
        )
        if not rows:
            return {"ar_total": 0, "ar_overdue": 0, "overdue_rate": 0, "risk_high_count": 0, "total_customers": 0}
        r = rows[0]
        return {
            "ar_total": r.get("ar_total") or 0,
            "ar_overdue": r.get("ar_overdue") or 0,
            "overdue_rate": r.get("overdue_rate") or 0,
            "risk_high_count": 0,
            "total_customers": r.get("total_customers") or 0,
        }

    def _get_mom_change(self) -> dict:
        rows = self._ch.execute_query(
            "SELECT "
            "  avgIf(ar_overdue / nullIf(ar_total, 0), ar_total > 0) AS curr_rate, "
            "  avgIf(prev_overdue / nullIf(prev_ar_total, 0), prev_ar_total > 0) AS prev_rate "
            "FROM ("
            "  SELECT "
            "    a.ar_overdue, a.ar_total, a.overdue_rate, "
            "    b.ar_overdue AS prev_overdue, b.ar_total AS prev_ar_total "
            "  FROM dm.dm_customer360 a "
            "  LEFT JOIN dm.dm_customer360 b "
            "    ON a.unified_customer_code = b.unified_customer_code "
            "   AND b.stat_date = (SELECT max(stat_date) - 7 FROM dm.dm_customer360) "
            "  WHERE a.stat_date = (SELECT max(stat_date) FROM dm.dm_customer360)"
            ")"
        )
        if not rows:
            return {"curr_rate": 0, "prev_rate": 0, "delta": 0}
        r = rows[0]
        curr = r.get("curr_rate") or 0
        prev = r.get("prev_rate") or 0
        return {
            "curr_rate": curr,
            "prev_rate": prev,
            "delta": curr - prev,
        }

    def _get_risk_customers(self) -> list[dict]:
        rows = self._ch.execute_query(
            "SELECT customer_name, ar_total, ar_overdue, overdue_rate, risk_level "
            "FROM dm.dm_customer360 "
            "WHERE stat_date = (SELECT max(stat_date) FROM dm.dm_customer360) "
            "  AND overdue_rate > 0.1 "
            "ORDER BY overdue_rate DESC LIMIT 10"
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

    def _get_concentration(self) -> list[dict]:
        rows = self._ch.execute_query(
            "SELECT customer_name, ar_total "
            "FROM dm.dm_customer360 "
            "WHERE stat_date = (SELECT max(stat_date) FROM dm.dm_customer360) "
            "ORDER BY ar_total DESC LIMIT 10"
        )
        total = sum(r.get("ar_total") or 0 for r in rows)
        return [
            {"name": r.get("customer_name", "?"), "amount": r.get("ar_total") or 0,
             "pct": (r.get("ar_total") or 0) / total if total > 0 else 0}
            for r in rows
        ]

    def _get_yoy_change(self) -> dict:
        """同比：当前月 vs 去年同月（取 12 个月前的 stat_date）"""
        rows = self._ch.execute_query(
            "SELECT "
            "  avgIf(ar_overdue / nullIf(ar_total, 0), ar_total > 0) AS curr_rate, "
            "  avgIf(prev_y.ar_overdue / nullIf(prev_y.ar_total, 0), prev_y.ar_total > 0) AS prev_year_rate "
            "FROM ("
            "  SELECT ar_overdue, ar_total "
            "  FROM dm.dm_customer360 "
            "  WHERE stat_date = (SELECT max(stat_date) FROM dm.dm_customer360)"
            ") AS cur "
            "CROSS JOIN ("
            "  SELECT ar_overdue, ar_total "
            "  FROM dm.dm_customer360 "
            "  WHERE stat_date = (SELECT max(stat_date) - interval 1 year FROM dm.dm_customer360)"
            ") AS prev_y"
        )
        if not rows:
            return {"curr_rate": 0, "prev_year_rate": 0, "delta": 0, "delta_pct": 0}
        r = rows[0]
        curr = r.get("curr_rate") or 0
        prev = r.get("prev_year_rate") or 0
        return {
            "curr_rate": curr,
            "prev_year_rate": prev,
            "delta": curr - prev,
            "delta_pct": ((curr - prev) / prev * 100) if prev != 0 else 0,
        }

    def _save_record(self, report_type: str, period_start: date, period_end: date, file_path: str) -> None:
        record_id = str(uuid.uuid4())
        recipients = '[{"recipient_id": "mgmt_1", "type": "management"}]'
        try:
            self._ch.execute(
                "INSERT INTO dm.report_records "
                "(id, report_type, period_start, period_end, recipients, file_path, sent_at, status) "
                "VALUES (%(id)s, %(report_type)s, %(period_start)s, %(period_end)s, %(recipients)s, %(file_path)s, now(), 'generated')",
                {
                    "id": record_id,
                    "report_type": report_type,
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "recipients": recipients,
                    "file_path": file_path,
                }
            )
        except Exception:
            pass

    def send_management_report(self, report_type: str) -> bool:
        """发送管理层报告到飞书群"""
        from services.feishu.config import get_feishu_config
        from services.feishu.feishu_client import FeishuClient

        config = get_feishu_config()
        if not config.mgmt_channel_id:
            return False

        today = date.today()
        filename = f"{report_type}_{today.isoformat()}.html"
        report_url = f"/static/reports/{filename}"

        card_elements = [
            {
                "tag": "markdown",
                "content": f"**📊 {'周报' if report_type == 'weekly' else '月报'} - {today.isoformat()}**\n"
                            f"已完成生成，点击下方按钮查看完整报告",
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看完整报告"},
                    "type": "primary",
                    "url": report_url,
                }]
            }
        ]

        client = FeishuClient()
        return client.send_card_to_channel({"elements": card_elements}, channel_id=config.mgmt_channel_id)
