"""业务员 AR 报告服务"""
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from services.clickhouse_service import ClickHouseDataService
from services.salesperson_mapping_service import SalespersonMappingService

PROJECT_ROOT = Path(__file__).parent.parent


class PerSalespersonReportService:
    """业务员 AR 报告生成"""

    def __init__(
        self,
        ch: ClickHouseDataService | None = None,
        mapping_service: SalespersonMappingService | None = None,
    ):
        self._ch = ch or ClickHouseDataService()
        self._mapping = mapping_service or SalespersonMappingService()
        self._jinja = Environment(
            loader=FileSystemLoader(PROJECT_ROOT / "templates" / "reports"),
            autoescape=True,
        )

    def generate_for_all(self, report_period: str = "weekly") -> list[str]:
        """为所有启用的业务员生成报告，返回文件路径列表"""
        active = self._mapping.list_active()
        files = []
        for rep in active:
            try:
                path = self.generate_for_salesperson(rep["salesperson_id"], report_period)
                if path:
                    files.append(path)
            except Exception:
                pass  # 单个失败不阻塞其他
        return files

    def generate_for_salesperson(
        self,
        salesperson_id: str,
        report_period: str = "weekly",
        today: date | None = None,
    ) -> str:
        """为指定业务员生成 AR 报告"""
        today = today or date.today()
        data = self._collect_report_data(salesperson_id, today, report_period)
        if data["customer_count"] == 0:
            return ""  # 无客户，跳过

        template = self._jinja.get_template("ar_per_salesperson.html.j2")
        html = template.render(
            salesperson_name=data["salesperson_name"],
            salesperson_id=salesperson_id,
            report_period=report_period,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            today=today.isoformat(),
            **data,
        )

        output_dir = PROJECT_ROOT / "static" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"ar_per_salesperson_{salesperson_id}_{today.isoformat()}.html"
        filepath = output_dir / filename
        filepath.write_text(html, encoding="utf-8")

        # 记录
        self._save_record(salesperson_id, report_period, str(filepath))
        return str(filepath)

    def _collect_report_data(
        self,
        salesperson_id: str,
        today: date,
        report_period: str,
    ) -> dict[str, Any]:
        # 获取业务员姓名
        active = self._mapping.list_active()
        rep = next((r for r in active if r["salesperson_id"] == salesperson_id), None)
        salesperson_name = rep["salesperson_name"] if rep else salesperson_id

        # 获取所负责客户
        customers = self._mapping.list_customers_by_salesperson(salesperson_id)
        if not customers:
            return {
                "salesperson_name": salesperson_name,
                "customer_count": 0,
                "summary": {},
                "customers": [],
            }

        # 查询 AR 数据（JOIN dm_customer360，取最近 stat_date）
        customer_ids = "', '".join(c["customer_id"] for c in customers)
        customer_names = "', '".join(c["customer_name"] for c in customers)

        ar_rows = self._ch.execute_query(
            f"SELECT "
            f"  customer_name, ar_total, ar_overdue, overdue_rate, risk_level "
            f"FROM dm.dm_customer360 "
            f"WHERE stat_date = (SELECT max(stat_date) FROM dm.dm_customer360) "
            f"  AND customer_id IN ('{customer_ids}') "
            f"ORDER BY overdue_rate DESC"
        )
        if not ar_rows:
            ar_rows = self._ch.execute_query(
                f"SELECT "
                f"  customer_name, ar_total, ar_overdue, overdue_rate, risk_level "
                f"FROM dm.dm_customer360 "
                f"WHERE stat_date = (SELECT max(stat_date) FROM dm.dm_customer360) "
                f"  AND customer_name IN ('{customer_names}') "
                f"ORDER BY overdue_rate DESC"
            )

        ar_total = sum(float(r.get("ar_total") or 0) for r in ar_rows)
        ar_overdue = sum(float(r.get("ar_overdue") or 0) for r in ar_rows)
        overdue_rate = ar_overdue / ar_total if ar_total > 0 else 0.0

        # 本周/本月新增逾期（取 alert_history 最近7天内）
        days = 7 if report_period == "weekly" else 30
        new_overdue_rows = self._ch.execute_query(
            f"SELECT count() AS cnt FROM dm.alert_history "
            f"WHERE triggered_at >= now() - INTERVAL {days} DAY "
            f"  AND metric = 'overdue_rate'"
        )
        new_overdue = new_overdue_rows[0]["cnt"] if new_overdue_rows else 0

        return {
            "salesperson_name": salesperson_name,
            "customer_count": len(ar_rows),
            "summary": {
                "ar_total": ar_total,
                "ar_overdue": ar_overdue,
                "overdue_rate": overdue_rate,
                "new_overdue": new_overdue,
            },
            "customers": [dict(r) for r in ar_rows],
        }

    def _save_record(self, salesperson_id: str, report_period: str, filepath: str) -> None:
        now = datetime.now().isoformat()
        record_id = str(uuid.uuid4())
        # period_start = today - 7 (周报) 或 today - 30 (月报)
        days_offset = 7 if report_period == "weekly" else 30
        period_start = (date.today() - timedelta(days=days_offset)).isoformat()
        period_end = date.today().isoformat()
        try:
            self._ch.execute(
                f"INSERT INTO dm.report_records "
                f"(id, report_type, period_start, period_end, recipients, file_path, sent_at, status, salesperson_id) "
                f"VALUES ('{record_id}', 'ar_per_salesperson', '{period_start}', '{period_end}', "
                f"'[\"{salesperson_id}\"]', '{filepath}', '{now}', 'generated', '{salesperson_id}')"
            )
        except Exception:
            pass
