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

    SLA_HIGH = 24.0    # hours
    SLA_MEDIUM = 72.0   # hours

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
            "  AND name NOT LIKE '%%\\_tmp' "
            "  AND engine NOT LIKE '%%Temp%%' "
            "  AND name NOT IN ('quality_reports', 'quality_anomalies') "
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
            f"SELECT name AS column_name, type FROM system.columns "
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
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        # 自动分析高危未分析异常
        from api.config import get_settings
        if get_settings().ai_analysis.auto_analyze_high_severity:
            unanalyzed = self._ch.execute_query(
                "SELECT id FROM dm.quality_anomalies "
                "WHERE severity = '高' AND root_cause = '' "
                "LIMIT 10"
            )
            for row in unanalyzed:
                try:
                    self.analyze_anomaly(row["id"])
                except Exception:
                    pass  # 不阻塞扫描主流程

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
        score = round(r.get("score_pct") or 100.0, 2)
        trend = self._compute_score_trend(stat_date, score)
        overdue = self._count_overdue_anomalies(stat_date)
        return {
            "stat_date": stat_date.isoformat(),
            "total_tables": r.get("total_tables") or 0,
            "total_fields": r.get("total_fields") or 0,
            "anomaly_count": r.get("anomaly_count") or 0,
            "high_severity": severity_map.get("高", 0),
            "medium_severity": severity_map.get("中", 0),
            "score_pct": score,
            "score_trend": trend,
            "overdue_count": overdue,
            "last_check_at": r.get("last_check_at"),
        }

    def _compute_score_trend(self, stat_date: date, current_score: float) -> str:
        """Compare current score to previous 2 scan dates. Returns improving/stable/degrading."""
        rows = self._ch.execute_query(
            "SELECT stat_date, avg(score_pct) AS score "
            "FROM dm.quality_reports "
            "WHERE stat_date < toDate('{sd}') "
            "GROUP BY stat_date "
            "ORDER BY stat_date DESC LIMIT 2".format(sd=stat_date.isoformat())
        )
        if len(rows) < 2:
            return "stable →"
        prev = rows[0].get("score", 100)
        prev2 = rows[1].get("score", 100)
        if current_score > prev and prev > prev2:
            return "improving ↓"
        if current_score < prev and prev < prev2:
            return "degrading ↑"
        return "stable →"

    def _count_overdue_anomalies(self, stat_date: date) -> int:
        """Count open anomalies past their SLA threshold."""
        rows = self._ch.execute_query(
            f"SELECT count() AS cnt FROM dm.quality_anomalies "
            f"WHERE stat_date = '{stat_date.isoformat()}' "
            f"  AND status = 'open' "
            f"  AND ("
            f"    (severity = '高' AND now() - detected_at > {self.SLA_HIGH} * 3600) "
            f"    OR (severity = '中' AND now() - detected_at > {self.SLA_MEDIUM} * 3600)"
            f"  )"
        )
        return rows[0].get("cnt", 0) if rows else 0

    def get_quality_history(self, days: int = 7) -> list[dict]:
        rows = self._ch.execute_query(
            f"SELECT "
            f"  stat_date, "
            f"  avg(score_pct) AS score_pct, "
            f"  sum(anomaly_count) AS anomaly_count "
            f"FROM dm.quality_reports "
            f"WHERE stat_date >= today() - {days} "
            f"GROUP BY stat_date "
            f"ORDER BY stat_date ASC"
        )
        result = []
        for r in rows:
            d = r["stat_date"].isoformat() if hasattr(r["stat_date"], "isoformat") else str(r["stat_date"])
            score = round(r.get("score_pct") or 100.0, 2)
            anom_rows = self._ch.execute_query(
                f"SELECT severity, count() AS cnt FROM dm.quality_anomalies "
                f"WHERE stat_date = '{d}' AND status = 'open' GROUP BY severity"
            )
            sev = {row["severity"]: row["cnt"] for row in anom_rows}
            result.append({
                "stat_date": d,
                "score_pct": score,
                "anomaly_count": r.get("anomaly_count") or 0,
                "high_severity": sev.get("高", 0),
                "medium_severity": sev.get("中", 0),
            })
        return result

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

    def list_anomalies(self, status: str | None, limit: int = 100, assignee: str | None = None) -> list[dict]:
        where_parts: list[str] = []
        if status:
            where_parts.append(f"status = '{status}'")
        else:
            where_parts.append("status = 'open'")
        if assignee:
            safe = assignee.replace("'", "''")
            where_parts.append(f"assignee = '{safe}'")
        where = " AND ".join(where_parts)
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

    def update_anomaly(self, anomaly_id: str, status: str | None = None, assignee: str | None = None) -> None:
        safe_id = anomaly_id.replace("'", "''")
        parts: list[str] = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if status is not None:
            if status not in ("resolved", "ignored"):
                raise ValueError(f"Invalid status: {status}")
            resolved_at = f"'{now_str}'" if status == "resolved" else "toDateTime('1970-01-01 00:00:00')"
            parts.append(f"status = '{status}', resolved_at = {resolved_at}")
        if assignee is not None:
            safe_assignee = assignee.replace("'", "''")
            parts.append(f"assignee = '{safe_assignee}'")

        if not parts:
            return

        self._ch.execute(
            f"ALTER TABLE dm.quality_anomalies UPDATE {', '.join(parts)} WHERE id = '{safe_id}'"
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
        # Trend data for Chart.js
        trend = self.get_quality_history(14)
        # Severity distribution
        sev_rows = self._ch.execute_query(
            f"SELECT severity, count() AS cnt FROM dm.quality_anomalies "
            f"WHERE stat_date = '{stat_date.isoformat()}' GROUP BY severity"
        )
        sev_map = {r["severity"]: r["cnt"] for r in sev_rows}
        severity_data = {
            "high": sev_map.get("高", 0),
            "medium": sev_map.get("中", 0),
            "low": sev_map.get("低", 0),
        }

        template = self._jinja.get_template("quality_report.html.j2")
        html = template.render(
            stat_date=stat_date.isoformat(),
            summary=summary,
            anomalies=[dict(a) for a in anomalies],
            trend_data=trend,
            severity_data=severity_data,
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

    def send_quality_digest(self, stat_date: date | None = None) -> dict:
        """Send daily digest: always sends email + DingTalk if configured."""
        from services.quality_alert_service import QualityAlertService
        from api.config import get_settings

        stat_date = stat_date or date.today()
        summary = self.get_summary(stat_date)
        anomalies = self.list_open_anomalies(limit=20)
        date_str = stat_date.isoformat()
        settings = get_settings()
        email_cfg = settings.quality_email
        dingtalk_cfg = settings.quality_dingtalk

        svc = QualityAlertService()
        email_count = 0
        dingtalk_ok = False

        if email_cfg and email_cfg.smtp_host:
            email_count = svc.send_quality_email(
                summary=summary,
                anomalies=anomalies,
                stat_date=date_str,
                smtp_host=email_cfg.smtp_host,
                smtp_port=email_cfg.smtp_port,
                smtp_user=email_cfg.smtp_user,
                smtp_password=email_cfg.smtp_password,
                from_addr=email_cfg.from_addr,
                to_addrs=email_cfg.to_addrs,
            )

        if dingtalk_cfg and dingtalk_cfg.webhook_url:
            dingtalk_ok = svc.send_dingtalk(
                summary=summary,
                anomalies=anomalies,
                stat_date=date_str,
                webhook_url=dingtalk_cfg.webhook_url,
            )

        return {"email_sent": email_count, "dingtalk_sent": 1 if dingtalk_ok else 0}

    def analyze_anomaly(self, anomaly_id: str) -> dict[str, Any] | None:
        """对指定异常执行 AI 根因分析"""
        from services.ai_analysis_service import AIGenAnalysisService

        rows = self._ch.execute_query(
            "SELECT * FROM dm.quality_anomalies WHERE id = %(id)s LIMIT 1",
            {"id": anomaly_id}
        )
        if not rows:
            return None
        row = rows[0]

        # 计算持续天数
        detected: datetime = row["detected_at"]
        duration_days = max(1, (datetime.now() - detected).days)

        # 调用 AI 分析
        ai_svc = AIGenAnalysisService()
        result = ai_svc.analyze(
            table_name=row["table_name"],
            column_name=row["column_name"],
            metric=row["metric"],
            value=float(row["value"]),
            threshold=float(row["threshold"]),
            duration_days=duration_days,
        )

        # 写入 ClickHouse（ReplacingMergeTree，同 id 行自动替换旧行）
        now = datetime.now()
        self._ch.execute(
            "INSERT INTO dm.quality_anomalies "
            "(id, report_id, stat_date, table_name, column_name, metric, value, threshold, "
            "severity, status, detected_at, resolved_at, assignee, sla_hours, "
            "root_cause, analyzed_at, model_used) "
            "VALUES "
            "(%(id)s, %(report_id)s, %(stat_date)s, %(table_name)s, %(column_name)s, %(metric)s, "
            "%(value)s, %(threshold)s, %(severity)s, %(status)s, %(detected_at)s, %(resolved_at)s, "
            "%(assignee)s, %(sla_hours)s, %(root_cause)s, %(analyzed_at)s, %(model_used)s)",
            {
                "id": anomaly_id,
                "report_id": row["report_id"],
                "stat_date": row["stat_date"],
                "table_name": row["table_name"],
                "column_name": row["column_name"],
                "metric": row["metric"],
                "value": row["value"],
                "threshold": row["threshold"],
                "severity": row["severity"],
                "status": row["status"],
                "detected_at": row["detected_at"],
                "resolved_at": row.get("resolved_at"),
                "assignee": row.get("assignee", ""),
                "sla_hours": row.get("sla_hours", 0.0),
                "root_cause": result["root_cause"],
                "analyzed_at": now,
                "model_used": result["model_used"],
            }
        )

        result["anomaly_id"] = anomaly_id
        result["analyzed_at"] = now.isoformat()
        return result

    def get_aggregated_anomalies(
        self,
        group_by: list[str],
        status: str | None = None,
        min_severity: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """多维度异常聚合视图"""
        # 构建 WHERE 子句（SQL 注入安全）
        conditions = []
        params: dict[str, Any] = {}
        if status:
            conditions.append("status = %(status)s")
            params["status"] = status
        if min_severity:
            # 级别过滤：min_severity="中" 时只显示 severity in ("高","中")
            sev_order = ["高", "中", "低"]
            min_idx = sev_order.index(min_severity)
            relevant_levels = sev_order[:min_idx + 1]
            sev_conditions = " OR ".join(
                f"severity = %(sev_{i})" for i, _ in enumerate(relevant_levels)
            )
            conditions.append(f"({sev_conditions})")
            for i, level in enumerate(relevant_levels):
                params[f"sev_{i}"] = level

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # 查询基础数据（带 ORDER BY 防止乱序）
        base_sql = (
            "SELECT id, table_name, column_name, metric, value, threshold, severity, "
            "status, assignee, detected_at "
            "FROM dm.quality_anomalies "
            f"{where_clause} "
            "ORDER BY detected_at DESC"
        )
        rows = self._ch.execute_query(base_sql, params)
        if not rows:
            return {"groups": [], "total_anomalies": 0}

        # 按 group_by 维度分组
        groups_map: dict[str, dict[str, Any]] = {}
        now_dt = datetime.now()

        for row in rows:
            # 生成复合 key
            key_parts = []
            for dim in group_by:
                if dim == "table":
                    key_parts.append(row["table_name"])
                elif dim == "assignee":
                    key_parts.append(row["assignee"] or "(unassigned)")
                elif dim == "severity":
                    key_parts.append(row["severity"])
            key = "::".join(key_parts) if key_parts else "all"

            if key not in groups_map:
                groups_map[key] = {
                    "key": key,
                    "total": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "unassigned": 0,
                    "oldest_age_days": 0,
                    "items": [],
                }
            g = groups_map[key]
            g["total"] += 1
            sev = row["severity"]
            g[sev] = g.get(sev, 0) + 1
            if not row["assignee"]:
                g["unassigned"] += 1

            detected: datetime = row["detected_at"]
            age_days = (now_dt - detected).days
            if age_days > g["oldest_age_days"]:
                g["oldest_age_days"] = age_days

            if len(g["items"]) < limit:
                g["items"].append({
                    "id": row["id"],
                    "table_name": row["table_name"],
                    "column_name": row["column_name"],
                    "severity": row["severity"],
                    "status": row["status"],
                    "assignee": row["assignee"] or "",
                    "created_at": detected.date().isoformat() if hasattr(detected, "date") else str(detected)[:10],
                })

        groups = list(groups_map.values())
        total = sum(g["total"] for g in groups)
        return {"groups": groups, "total_anomalies": total}
