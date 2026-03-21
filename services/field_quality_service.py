"""字段级数据质量检查服务"""
import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from services.clickhouse_service import ClickHouseDataService

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent


class FieldQualityService:
    """字段级数据质量检查"""

    THRESHOLDS = {
        "null_rate":       {"high": 0.20, "medium": 0.10},
        "distinct_rate":   {"high": 0.999, "medium": 0.99},
        "negative_rate":   {"high": 0.05, "medium": 0.02},
        "freshness_hours": {"high": 72, "medium": 48},
    }

    RATIO_METRICS = {"null_rate", "distinct_rate", "negative_rate"}

    def __init__(self, ch: ClickHouseDataService | None = None):
        self._ch = ch or ClickHouseDataService()
        self._jinja = Environment(
            loader=FileSystemLoader(str(PROJECT_ROOT / "templates" / "reports")),
            autoescape=True,
        )

    # ------------------------------------------------------------------
    # Table / column discovery
    # ------------------------------------------------------------------

    def list_monitored_tables(self) -> list[str]:
        rows = self._ch.execute_query(
            "SELECT database, name FROM system.tables "
            "WHERE database IN ('raw', 'std', 'dm') "
            "  AND name NOT LIKE '%\\_tmp' "
            "  AND engine NOT LIKE '%Temp%' "
            "ORDER BY database, name"
        )
        return [f"{r['database']}.{r['name']}" for r in rows]

    def list_columns(self, table_name: str) -> list[dict[str, str]]:
        db, name = table_name.split(".", 1)
        # Whitelist db and escape table name to prevent SQL injection
        if db not in ("raw", "std", "dm"):
            return []
        safe_name = name.replace("'", "''")
        rows = self._ch.execute_query(
            f"SELECT column_name, type FROM system.columns "
            f"WHERE database = '{db}' AND table = '{safe_name}' "
            f"ORDER BY position"
        )
        return rows

    def _has_etl_time(self, table_name: str) -> bool:
        cols = self.list_columns(table_name)
        return any(c["column_name"] == "etl_time" for c in cols)

    def _build_filter_clause(self, table_name: str, stat_date_iso: str) -> str:
        if self._has_etl_time(table_name):
            return f"toDate(etl_time) = '{stat_date_iso}'"
        return "1=1"

    # ------------------------------------------------------------------
    # Per-column checks
    # ------------------------------------------------------------------

    def check_column(
        self,
        table_name: str,
        column_name: str,
        stat_date: date,
    ) -> list[dict[str, Any]]:
        cols = self.list_columns(table_name)
        if column_name not in {c["column_name"] for c in cols}:
            return []
        col_type = next(c["type"] for c in cols if c["column_name"] == column_name)
        today_str = stat_date.isoformat()
        filter_clause = self._build_filter_clause(table_name, today_str)
        qcol = f"`{column_name}`"
        anomalies: list[dict[str, Any]] = []

        # null_rate — all types
        rows = self._ch.execute_query(
            f"SELECT countIf({qcol} IS NULL) / count() AS v "
            f"FROM {table_name} WHERE {filter_clause}"
        )
        null_rate = float(rows[0]["v"]) if rows else 0.0
        t = self.THRESHOLDS["null_rate"]
        if null_rate > t["high"]:
            anomalies.append(self._make_anomaly(table_name, column_name, "null_rate", null_rate, t["high"], "高"))
        elif null_rate > t["medium"]:
            anomalies.append(self._make_anomaly(table_name, column_name, "null_rate", null_rate, t["medium"], "中"))

        # distinct_rate — all types
        rows = self._ch.execute_query(
            f"SELECT uniqExact({qcol}) / count() AS v "
            f"FROM {table_name} WHERE {filter_clause}"
        )
        distinct_rate = float(rows[0]["v"]) if rows else 0.0
        t = self.THRESHOLDS["distinct_rate"]
        if distinct_rate > t["high"]:
            anomalies.append(self._make_anomaly(table_name, column_name, "distinct_rate", distinct_rate, t["high"], "中"))
        elif distinct_rate > t["medium"]:
            anomalies.append(self._make_anomaly(table_name, column_name, "distinct_rate", distinct_rate, t["medium"], "低"))

        # negative_rate — numeric types only
        if self._should_check_negative_rate(col_type):
            rows = self._ch.execute_query(
                f"SELECT countIf({qcol} < 0) / count() AS v "
                f"FROM {table_name} WHERE {filter_clause}"
            )
            neg = float(rows[0]["v"]) if rows else 0.0
            t = self.THRESHOLDS["negative_rate"]
            if neg > t["high"]:
                anomalies.append(self._make_anomaly(table_name, column_name, "negative_rate", neg, t["high"], "高"))
            elif neg > t["medium"]:
                anomalies.append(self._make_anomaly(table_name, column_name, "negative_rate", neg, t["medium"], "中"))

        # freshness_hours — all types, only if table has etl_time
        if self._has_etl_time(table_name):
            rows = self._ch.execute_query(
                f"SELECT now() - MAX(etl_time) AS v FROM {table_name}"
            )
            hours = float(rows[0]["v"]) if rows else 0.0
            t = self.THRESHOLDS["freshness_hours"]
            if hours > t["high"]:
                anomalies.append(self._make_anomaly(table_name, column_name, "freshness_hours", hours, t["high"], "中"))
            elif hours > t["medium"]:
                anomalies.append(self._make_anomaly(table_name, column_name, "freshness_hours", hours, t["medium"], "低"))

        return anomalies

    def _should_check_negative_rate(self, col_type: str) -> bool:
        return any(col_type.startswith(p) for p in ("Int", "UInt", "Float", "Decimal"))

    def _make_anomaly(
        self, table_name: str, column_name: str,
        metric: str, value: float, threshold: float, severity: str,
    ) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "table_name": table_name,
            "column_name": column_name,
            "metric": metric,
            "value": value,
            "threshold": threshold,
            "severity": severity,
        }

    # ------------------------------------------------------------------
    # Full scan (per-table error isolation)
    # ------------------------------------------------------------------

    def check_all(self, stat_date: date | None = None) -> dict[str, Any]:
        stat_date = stat_date or date.today()
        today_str = stat_date.isoformat()
        now_str = datetime.now().isoformat()
        report_id = str(uuid.uuid4())

        tables = self.list_monitored_tables()
        total_fields = 0
        all_anomalies: list[dict] = []
        table_scores: list[float] = []

        for table_name in tables:
            try:
                cols = self.list_columns(table_name)
                normal_count = 0
                table_anomalies: list[dict] = []
                for col in cols:
                    ca = self.check_column(table_name, col["column_name"], stat_date)
                    total_fields += 1
                    if ca:
                        table_anomalies.extend(ca)
                    else:
                        normal_count += 1
                all_anomalies.extend(table_anomalies)
                score_pct = (normal_count / len(cols) * 100) if cols else 100.0
                table_scores.append(score_pct)

                self._ch.execute(
                    f"INSERT INTO dm.quality_reports "
                    f"(id, stat_date, table_name, total_fields, anomaly_count, score_pct, generated_at) "
                    f"VALUES ('{report_id}', '{today_str}', '{table_name}', {len(cols)}, "
                    f"{len(table_anomalies)}, {score_pct:.2f}, '{now_str}')"
                )
            except Exception as e:
                logger.warning(f"[FieldQuality] Skipping {table_name}: {e}")
                continue

        for a in all_anomalies:
            self._ch.execute(
                f"INSERT INTO dm.quality_anomalies "
                f"(id, report_id, stat_date, table_name, column_name, metric, value, threshold, severity, status, detected_at, resolved_at) "
                f"VALUES ('{a['id']}', '{report_id}', '{today_str}', '{a['table_name']}', '{a['column_name']}', "
                f"'{a['metric']}', {a['value']:.6f}, {a['threshold']:.6f}, '{a['severity']}', 'open', '{now_str}', toDateTime('1970-01-01 00:00:00'))"
            )

        overall_score = sum(table_scores) / len(table_scores) if table_scores else 100.0
        self.generate_report_html(stat_date)  # write HTML after persisting results
        return {
            "report_id": report_id,
            "stat_date": today_str,
            "total_tables": len(tables),
            "total_fields": total_fields,
            "anomaly_count": len(all_anomalies),
            "score_pct": round(overall_score, 2),
        }

    # ------------------------------------------------------------------
    # Query helpers (used by API routes)
    # ------------------------------------------------------------------

    def get_summary(self, stat_date: date | None = None) -> dict[str, Any]:
        stat_date = stat_date or date.today()
        rows = self._ch.execute_query(
            f"SELECT "
            f"  count(DISTINCT table_name) AS total_tables, "
            f"  sum(total_fields) AS total_fields, "
            f"  sum(anomaly_count) AS anomaly_count, "
            f"  avg(score_pct) AS score_pct, "
            f"  max(generated_at) AS last_check_at "
            f"FROM dm.quality_reports "
            f"WHERE stat_date = '{stat_date.isoformat()}'"
        )
        anomaly_rows = self._ch.execute_query(
            f"SELECT severity, count() AS cnt "
            f"FROM dm.quality_anomalies "
            f"WHERE stat_date = '{stat_date.isoformat()}' AND status = 'open' "
            f"GROUP BY severity"
        )
        severity_map = {r["severity"]: r["cnt"] for r in anomaly_rows}
        r = rows[0] if rows else {}
        return {
            "stat_date": stat_date.isoformat(),
            "total_tables": r.get("total_tables") or 0,
            "total_fields": r.get("total_fields") or 0,
            "anomaly_count": r.get("anomaly_count") or 0,
            "high_severity": severity_map.get("高", 0),
            "medium_severity": severity_map.get("中", 0),
            "score_pct": round(r.get("score_pct") or 100.0, 2),
            "last_check_at": r.get("last_check_at"),
        }

    def list_reports(self, stat_date: date, limit: int = 50) -> list[dict]:
        return self._ch.execute_query(
            f"SELECT * FROM dm.quality_reports "
            f"WHERE stat_date = '{stat_date.isoformat()}' "
            f"ORDER BY generated_at DESC LIMIT {limit}"
        )

    def get_report(self, report_id: str) -> dict | None:
        rows = self._ch.execute_query(f"SELECT * FROM dm.quality_reports WHERE id = '{report_id}' LIMIT 1")
        return rows[0] if rows else None

    def list_anomalies_by_report(self, report_id: str) -> list[dict]:
        return self._ch.execute_query(
            f"SELECT * FROM dm.quality_anomalies "
            f"WHERE report_id = '{report_id}' "
            f"ORDER BY severity DESC, detected_at DESC"
        )

    def list_anomalies(self, status: str | None, limit: int = 100) -> list[dict]:
        where = f"status = '{status}'" if status else "1=1"
        return self._ch.execute_query(
            f"SELECT * FROM dm.quality_anomalies "
            f"WHERE {where} "
            f"ORDER BY severity DESC, detected_at DESC LIMIT {limit}"
        )

    def list_open_anomalies(self, limit: int = 100) -> list[dict]:
        return self._ch.execute_query(
            f"SELECT * FROM dm.quality_anomalies "
            f"WHERE status = 'open' "
            f"ORDER BY severity DESC, detected_at DESC LIMIT {limit}"
        )

    def update_anomaly(self, anomaly_id: str, status: str) -> None:
        # Whitelist status to prevent SQL injection
        if status not in ("resolved", "ignored"):
            raise ValueError(f"Invalid status: {status}")
        # Escape anomaly_id (UUID, but defensive)
        safe_id = anomaly_id.replace("'", "''")
        now_str = datetime.now().isoformat()
        resolved_at = f"'{now_str}'" if status == "resolved" else "toDateTime('1970-01-01 00:00:00')"
        self._ch.execute(
            f"ALTER TABLE dm.quality_anomalies "
            f"UPDATE status = '{status}', resolved_at = {resolved_at} "
            f"WHERE id = '{safe_id}'"
        )

    # ------------------------------------------------------------------
    # HTML report
    # ------------------------------------------------------------------

    def generate_report_html(self, stat_date: date | None = None) -> str:
        stat_date = stat_date or date.today()
        summary = self.get_summary(stat_date)
        anomalies = self._ch.execute_query(
            f"SELECT * FROM dm.quality_anomalies "
            f"WHERE stat_date = '{stat_date.isoformat()}' "
            f"ORDER BY severity DESC, detected_at DESC LIMIT 200"
        )
        template = self._jinja.get_template("quality_report.html.j2")
        html = template.render(
            stat_date=stat_date.isoformat(),
            summary=summary,
            anomalies=[dict(a) for a in anomalies],
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        output_dir = PROJECT_ROOT / "static" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        dated = output_dir / f"quality_report_{stat_date.isoformat()}.html"
        dated.write_text(html, encoding="utf-8")
        latest = output_dir / "quality_report_latest.html"
        latest.write_text(html, encoding="utf-8")
        return str(dated)

    # ------------------------------------------------------------------
    # Feishu card
    # ------------------------------------------------------------------

    def send_feishu_card(self, stat_date: date | None = None) -> None:
        from services.feishu.feishu_client import FeishuClient
        from api.config import get_settings

        summary = self.get_summary(stat_date)
        if summary["anomaly_count"] == 0:
            return
        settings = get_settings()
        channel_id = settings.feishu.mgmt_channel_id
        if not channel_id:
            return

        client = FeishuClient()
        date_str = (stat_date or date.today()).isoformat()
        anomalies = self.list_open_anomalies(limit=10)
        high = [a for a in anomalies if a["severity"] == "高"]
        medium = [a for a in anomalies if a["severity"] == "中"]

        def fmt_val(metric: str, value: float) -> str:
            if metric in self.RATIO_METRICS:
                return f"{value:.1%}"
            return f"{value:.1f}h"

        card = {
            "header": {
                "title": {"tag": "plain_text", "content": f"数据质量日报 - {date_str}"},
                "template": "red",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"**监控 {summary['total_tables']} 张表 / {summary['total_fields']} 个字段**\n"
                        f"⚠️ 异常 **{summary['anomaly_count']}** 个（高危 {summary['high_severity']} / 中危 {summary['medium_severity']}）\n"
                        f"健康度 **{summary['score_pct']}%**"
                    ),
                },
                {"tag": "hr"},
            ],
        }

        if high:
            lines = "\n".join(
                f"- `{a['table_name']}.{a['column_name']}` — {a['metric']} {fmt_val(a['metric'], a['value'])}（阈值 {fmt_val(a['metric'], a['threshold'])})"
                for a in high
            )
            card["elements"].append({"tag": "markdown", "content": f"**高危（{len(high)}）**\n{lines}"})
        if medium:
            lines = "\n".join(
                f"- `{a['table_name']}.{a['column_name']}` — {a['metric']} {fmt_val(a['metric'], a['value'])}（阈值 {fmt_val(a['metric'], a['threshold'])})"
                for a in medium
            )
            card["elements"].append({"tag": "markdown", "content": f"**中危（{len(medium)}）**\n{lines}"})

        card["elements"].append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看看板"},
                "type": "primary",
                "url": "/static/reports/quality_report_latest.html",
            }],
        })

        client.send_card_to_channel(card, channel_id=channel_id)
