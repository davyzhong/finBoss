"""数据质量告警服务：Email + DingTalk"""
import logging
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class QualityAlertService:
    """质量告警发送服务"""

    # SLA thresholds in hours
    SLA_HIGH = 24.0   # high-severity: resolve within 24h
    SLA_MEDIUM = 72.0  # medium-severity: resolve within 72h

    def send_quality_email(
        self,
        summary: dict[str, Any],
        anomalies: list[dict],
        stat_date: str,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_addr: str,
        to_addrs: list[str],
    ) -> int:
        """Send quality digest email. Returns number of recipients sent to."""
        if not to_addrs:
            return 0
        body = self._build_email_body(summary, anomalies, stat_date)
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[FinBoss] 数据质量日报 {stat_date}"
            msg["From"] = from_addr
            msg["To"] = ", ".join(to_addrs)
            msg.attach(MIMEText(body, "html", "utf-8"))
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, to_addrs, msg.as_bytes())
            logger.info(f"[QualityAlertService] Email sent to {len(to_addrs)} recipients")
            return len(to_addrs)
        except Exception as e:
            logger.error(f"[QualityAlertService] Email send failed: {e}")
            return 0

    def send_dingtalk(
        self,
        summary: dict[str, Any],
        anomalies: list[dict],
        stat_date: str,
        webhook_url: str,
    ) -> bool:
        """Send quality alert to DingTalk webhook. Returns True on success."""
        if not webhook_url:
            return False
        severity_map = {a["severity"] for a in anomalies}
        has_high = "高" in severity_map
        body = self._build_dingtalk_body(summary, anomalies, stat_date, has_high)
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(webhook_url, json=body)
                if resp.status_code == 200:
                    logger.info("[QualityAlertService] DingTalk alert sent")
                    return True
                logger.warning(f"[QualityAlertService] DingTalk returned {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"[QualityAlertService] DingTalk send failed: {e}")
            return False

    def _build_email_body(
        self, summary: dict[str, Any], anomalies: list[dict], stat_date: str
    ) -> str:
        high = [a for a in anomalies if a["severity"] == "高"]
        medium = [a for a in anomalies if a["severity"] == "中"]
        score = summary.get("score_pct", 100)
        score_color = "#e53e3e" if score < 90 else "#d69e2e" if score < 95 else "#276749"
        anomaly_rows = ""
        RATIO_METRICS = {"null_rate", "distinct_rate", "negative_rate"}
        for a in (high + medium)[:20]:
            val_str = f"{a['value']:.1%}" if a["metric"] in RATIO_METRICS else f"{a['value']:.1f}h"
            thr_str = f"{a['threshold']:.1%}" if a["metric"] in RATIO_METRICS else f"{a['threshold']:.1f}h"
            anomaly_rows += f"<tr><td>{a['table_name']}</td><td>{a['column_name']}</td>"
            anomaly_rows += f"<td>{a['metric']}</td><td>{val_str}</td><td>{thr_str}</td>"
            anomaly_rows += f"<td style='color:{'#c53030' if a['severity']=='高' else '#975a16'}'>{a['severity']}</td></tr>"

        return f"""<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:700px;margin:0 auto;">
<h2 style="color:#2d3748;">数据质量日报 — {stat_date}</h2>
<div style="background:#f7fafc;padding:16px;border-radius:8px;margin-bottom:16px;">
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;text-align:center;">
    <div><div style="font-size:24px;font-weight:700">{summary.get('total_tables', 0)}</div><div style="color:#718096;font-size:12px">监控表数</div></div>
    <div><div style="font-size:24px;font-weight:700">{summary.get('total_fields', 0)}</div><div style="color:#718096;font-size:12px">监控字段</div></div>
    <div><div style="font-size:24px;font-weight:700;color:#e53e3e">{summary.get('anomaly_count', 0)}</div><div style="color:#718096;font-size:12px">异常数</div></div>
    <div><div style="font-size:24px;font-weight:700;color:{score_color}">{score:.1f}%</div><div style="color:#718096;font-size:12px">健康度</div></div>
  </div>
</div>
<h3 style="margin-top:24px;">{'⚠️ 高危异常' if high else '✅ 无高危异常'} {'(' + str(len(high)) + ')' if high else ''}</h3>
{'无' if not high else f'<p>共 {len(high)} 个高危异常</p>'}
<h3 style="margin-top:16px;">{'⚠️ 中危异常' if medium else '✅ 无中危异常'} {'(' + str(len(medium)) + ')' if medium else ''}</h3>
{'<p>无</p>' if not medium else f'<p>共 {len(medium)} 个中危异常</p>'}
<table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:14px;">
  <thead><tr style="background:#edf2f7"><th>表名</th><th>字段</th><th>指标</th><th>当前值</th><th>阈值</th><th>级别</th></tr></thead>
  <tbody>{anomaly_rows or '<tr><td colspan="6" style="color:#718096">无</td></tr>'}</tbody>
</table>
<p style="margin-top:24px;color:#a0aec0;font-size:12px">FinBoss 数据质量监控 | {stat_date}</p>
</body></html>"""

    def _build_dingtalk_body(
        self, summary: dict[str, Any], anomalies: list[dict], stat_date: str, has_high: bool
    ) -> dict:
        high = [a for a in anomalies if a["severity"] == "高"][:5]
        medium = [a for a in anomalies if a["severity"] == "中"][:5]
        RATIO_METRICS = {"null_rate", "distinct_rate", "negative_rate"}
        lines = [f"数据质量日报 — {stat_date}"]
        lines.append(f"监控 {summary.get('total_tables', 0)} 表 / {summary.get('total_fields', 0)} 字段")
        lines.append(f"⚠️ 异常 {summary.get('anomaly_count', 0)} 个（高危 {summary.get('high_severity', 0)} / 中危 {summary.get('medium_severity', 0)}）")
        lines.append(f"健康度 {summary.get('score_pct', 100):.1f}%")
        if high:
            lines.append("---高危---")
            for a in high:
                m = a["metric"]
                v = f"{a['value']:.1%}" if m in RATIO_METRICS else f"{a['value']:.1f}h"
                lines.append(f"- {a['table_name']}.{a['column_name']} {m}={v}")
        if medium:
            lines.append("---中危---")
            for a in medium:
                m = a["metric"]
                v = f"{a['value']:.1%}" if m in RATIO_METRICS else f"{a['value']:.1f}h"
                lines.append(f"- {a['table_name']}.{a['column_name']} {m}={v}")
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"数据质量日报 {stat_date}",
                "text": "\n\n".join(lines),
            },
        }
