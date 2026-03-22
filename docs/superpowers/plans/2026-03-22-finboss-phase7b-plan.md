# Phase 7B - 数据质量监控增强

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add trend tracking, anomaly ownership + SLA tracking, multi-channel alerts (email + DingTalk), and interactive Chart.js HTML reports to the Phase 7A quality monitoring system.

**Architecture:** Phase 7B extends `FieldQualityService` with trend/SLA computation, introduces a new `AlertService` for email/DingTalk delivery, and upgrades the Jinja2 HTML report with Chart.js visualizations. The scheduler runs a daily email digest at 07:00 after the 06:00 quality scan.

**Tech Stack:** Python 3.11, FastAPI, APScheduler, Jinja2, Chart.js (CDN), smtplib, httpx (DingTalk)

---

## File Map

```
CREATE: scripts/phase7b_ddl.sql           # ALTER TABLE quality_anomalies
CREATE: scripts/init_phase7b.py            # Apply column additions idempotently
MODIFY: schemas/quality.py                 # Add assignee, sla_hours to QualityAnomaly
MODIFY: api/schemas/quality.py             # New response models
MODIFY: services/field_quality_service.py  # +trend, SLA, history, overdue, assignee
CREATE: services/alert_service.py           # send_quality_email, send_dingtalk
MODIFY: api/routes/quality.py             # +/history, +/send-digest, ?assignee=
MODIFY: api/config.py                     # +EmailConfig, +DingTalkConfig
MODIFY: templates/reports/quality_report.html.j2  # Chart.js charts
MODIFY: services/scheduler_service.py       # Daily digest email job (07:00)
CREATE: tests/unit/test_quality_trend_sla.py
MODIFY: tests/integration/test_quality_api.py
```

---

## Implementation Notes

### ClickHouse `execute()` note
All INSERT/ALTER statements use inline values (no named params). Use `.strftime("%Y-%m-%d %H:%M:%S")` for DateTime columns. Escape all interpolated strings defensively.

### Test isolation
Mock `ClickHouseDataService` via `patch("services.field_quality_service.ClickHouseDataService")` — not `services.clickhouse_service.ClickHouseDataService`.

---

## Task 1: DDL + Init Script

**Files:**
- Create: `scripts/phase7b_ddl.sql`
- Create: `scripts/init_phase7b.py`
- Run: `uv run python scripts/init_phase7b.py`

### `scripts/phase7b_ddl.sql`
```sql
-- Phase 7B DDL: Add assignee, sla_hours columns to dm.quality_anomalies
ALTER TABLE dm.quality_anomalies
  ADD COLUMN IF NOT EXISTS assignee String DEFAULT '';

ALTER TABLE dm.quality_anomalies
  ADD COLUMN IF NOT EXISTS sla_hours Float64 DEFAULT 0;
```

### `scripts/init_phase7b.py`
```python
"""Phase 7B 增量 DDL：添加 assignee / sla_hours 列"""
import logging
from pathlib import Path

from clickhouse_driver.errors import Error as ClickHouseError

from services.clickhouse_service import ClickHouseDataService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
DDL_FILE = SCRIPT_DIR / "phase7b_ddl.sql"


def init_phase7b() -> None:
    if not DDL_FILE.exists():
        raise FileNotFoundError(f"DDL file not found: {DDL_FILE}")

    ch = ClickHouseDataService()
    statements = [s.strip() for s in DDL_FILE.read_text(encoding="utf-8").split(";") if s.strip()]

    for stmt in statements:
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            logger.info(f"OK: {stmt[:60]}")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 44:
                logger.info(f"SKIP (already exists): {stmt[:60]}")
            else:
                logger.error(f"FAIL: {stmt[:60]} — {e}")
                raise

    logger.info("Phase 7B DDL done.")


if __name__ == "__main__":
    init_phase7b()
```

- [ ] **Step 1: Write the DDL and init script files**

- [ ] **Step 2: Run init script**

Run: `uv run python scripts/init_phase7b.py`
Expected: `INFO: Phase 7B DDL done.`

- [ ] **Step 3: Commit**

```bash
git add scripts/phase7b_ddl.sql scripts/init_phase7b.py
git commit -m "feat(7B): add assignee/sla_hours columns to quality_anomalies"
```

---

## Task 2: Schema + API Schema Updates

**Files:**
- Modify: `schemas/quality.py` (add fields)
- Modify: `api/schemas/quality.py` (add new models)

### Changes to `schemas/quality.py`

Add to `QualityAnomaly`:
```python
    assignee: str = ""
    sla_hours: float = 0.0
```

### Changes to `api/schemas/quality.py`

Add new models before the end of the file:
```python
class QualitySummaryResponse(BaseModel):
    stat_date: date
    total_tables: int
    total_fields: int
    anomaly_count: int
    high_severity: int
    medium_severity: int
    score_pct: float
    score_trend: str  # "improving ↓" | "stable →" | "degrading ↑"
    overdue_count: int  # open anomalies past SLA
    last_check_at: datetime | None


class QualityHistoryPoint(BaseModel):
    stat_date: date
    score_pct: float
    anomaly_count: int
    high_severity: int
    medium_severity: int


class QualityHistoryResponse(BaseModel):
    points: list[QualityHistoryPoint]
    score_trend: str  # "improving ↓" | "stable →" | "degrading ↑"


class AnomalyUpdateRequest(BaseModel):
    status: Literal["resolved", "ignored"] | None = None
    assignee: str | None = None
    note: str | None = None


class SendDigestResponse(BaseModel):
    status: str
    email_sent: int
    dingtalk_sent: int
```

- [ ] **Step 1: Update `schemas/quality.py`** — add `assignee` and `sla_hours` to `QualityAnomaly`

- [ ] **Step 2: Update `api/schemas/quality.py`** — add new models above

- [ ] **Step 3: Commit**

```bash
git add schemas/quality.py api/schemas/quality.py
git commit -m "feat(7B): add assignee/sla_hours to QualityAnomaly, new API schemas"
```

---

## Task 3: Alert Service (Email + DingTalk)

**Files:**
- Create: `services/alert_service.py`

### `services/alert_service.py`

```python
"""数据质量告警服务：Email + DingTalk"""
import logging
import smtplip
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AlertService:
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
        severity_map = {a["severity"] for a in anomalies}
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
            logger.info(f"[AlertService] Email sent to {len(to_addrs)} recipients")
            return len(to_addrs)
        except Exception as e:
            logger.error(f"[AlertService] Email send failed: {e}")
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
                    logger.info("[AlertService] DingTalk alert sent")
                    return True
                logger.warning(f"[AlertService] DingTalk returned {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"[AlertService] DingTalk send failed: {e}")
            return False

    def _build_email_body(
        self, summary: dict[str, Any], anomalies: list[dict], stat_date: str
    ) -> str:
        high = [a for a in anomalies if a["severity"] == "高"]
        medium = [a for a in anomalies if a["severity"] == "中"]
        score = summary.get("score_pct", 100)
        score_color = "#e53e3e" if score < 90 else "#d69e2e" if score < 95 else "#276749"
        anomaly_rows = ""
        for a in (high + medium)[:20]:
            val_str = f"{a['value']:.1%}" if a["metric"] in {"null_rate", "distinct_rate", "negative_rate"} else f"{a['value']:.1f}h"
            thr_str = f"{a['threshold']:.1%}" if a["metric"] in {"null_rate", "distinct_rate", "negative_rate"} else f"{a['threshold']:.1f}h"
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
        lines = [f"数据质量日报 — {stat_date}"]
        lines.append(f"监控 {summary.get('total_tables', 0)} 表 / {summary.get('total_fields', 0)} 字段")
        lines.append(f"⚠️ 异常 {summary.get('anomaly_count', 0)} 个（高危 {summary.get('high_severity', 0)} / 中危 {summary.get('medium_severity', 0)}）")
        lines.append(f"健康度 {summary.get('score_pct', 100):.1f}%")
        if high:
            lines.append("---高危---")
            for a in high:
                m = a["metric"]
                v = f"{a['value']:.1%}" if m in {"null_rate", "distinct_rate", "negative_rate"} else f"{a['value']:.1f}h"
                lines.append(f"- {a['table_name']}.{a['column_name']} {m}={v}")
        if medium:
            lines.append("---中危---")
            for a in medium:
                m = a["metric"]
                v = f"{a['value']:.1%}" if m in {"null_rate", "distinct_rate", "negative_rate"} else f"{a['value']:.1f}h"
                lines.append(f"- {a['table_name']}.{a['column_name']} {m}={v}")
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"数据质量日报 {stat_date}",
                "text": "\n\n".join(lines),
            },
        }
```

- [ ] **Step 1: Write `services/alert_service.py`**

- [ ] **Step 2: Fix smtplib import typo** — `import smtplib` (not `smtplip`) and `smtplib.SMTP` (not `smtplib.smtplib`)

- [ ] **Step 3: Commit**

```bash
git add services/alert_service.py
git commit -m "feat(7B): add AlertService with send_quality_email and send_dingtalk"
```

---

## Task 4: FieldQualityService Extensions

**Files:**
- Modify: `services/field_quality_service.py`

### Changes needed:

**1. SLA constants** (add after `RATIO_METRICS`):
```python
SLA_HIGH = 24.0    # hours
SLA_MEDIUM = 72.0   # hours
```

**2. `get_summary()` — add `score_trend` and `overdue_count`**:

Replace the existing `get_summary` method with:
```python
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
```

**3. Add helper methods** (after `get_summary`):

```python
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
        f"    (severity = '高' AND now() - detected_at > {SLA_HIGH} * 3600) "
        f"    OR (severity = '中' AND now() - detected_at > {SLA_MEDIUM} * 3600)"
        f"  )"
    )
    return rows[0].get("cnt", 0) if rows else 0
```

**4. `update_anomaly()` — support `assignee` parameter**:

Replace `update_anomaly` with:
```python
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
```

**5. `get_quality_history()` method** (new, after `_count_overdue_anomalies`):
```python
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
```

**6. `send_quality_digest()` method** (new, after `send_feishu_card`):
```python
def send_quality_digest(self, stat_date: date | None = None) -> dict:
    """Send daily digest: always sends email + DingTalk if configured."""
    from services.alert_service import AlertService
    from api.config import get_settings

    stat_date = stat_date or date.today()
    summary = self.get_summary(stat_date)
    anomalies = self.list_open_anomalies(limit=20)
    date_str = stat_date.isoformat()
    settings = get_settings()
    email_cfg = getattr(settings, "quality_email", None)
    dingtalk_cfg = getattr(settings, "quality_dingtalk", None)

    svc = AlertService()
    email_count = 0
    dingtalk_ok = False

    if email_cfg:
        email_count = svc.send_quality_email(
            summary=summary,
            anomalies=anomalies,
            stat_date=date_str,
            smtp_host=email_cfg.get("smtp_host", "localhost"),
            smtp_port=email_cfg.get("smtp_port", 587),
            smtp_user=email_cfg.get("smtp_user", ""),
            smtp_password=email_cfg.get("smtp_password", ""),
            from_addr=email_cfg.get("from_addr", "finboss@example.com"),
            to_addrs=email_cfg.get("to_addrs", []),
        )

    if dingtalk_cfg:
        dingtalk_ok = svc.send_dingtalk(
            summary=summary,
            anomalies=anomalies,
            stat_date=date_str,
            webhook_url=dingtalk_cfg.get("webhook_url", ""),
        )

    return {"email_sent": email_count, "dingtalk_sent": 1 if dingtalk_ok else 0}
```

- [ ] **Step 1: Apply all changes to `services/field_quality_service.py`**

- [ ] **Step 2: Verify `smtplib` import is correct** (not `smtplip`)

- [ ] **Step 3: Run tests** — `uv run pytest tests/unit/test_field_quality_service.py -v -k "trend or overdue or history or update_anomaly" 2>&1 | tail -20`

- [ ] **Step 4: Commit**

```bash
git add services/field_quality_service.py
git commit -m "feat(7B): extend FieldQualityService with trend/SLA/history/digest"
```

---

## Task 5: API Routes Updates

**Files:**
- Modify: `api/routes/quality.py`
- Modify: `api/dependencies.py`

### Changes to `api/routes/quality.py`

**1. Update imports** — add `QualityHistoryResponse`, `SendDigestResponse`:
```python
from api.schemas.quality import (
    AnomalyUpdateRequest,
    CheckResponse,
    QualityHistoryResponse,
    QualitySummaryResponse,
    SendDigestResponse,
)
```

**2. Update `get_quality_summary`** — no change needed (service returns `score_trend` and `overdue_count` now)

**3. Update `list_anomalies`** — add `assignee` query param:
```python
@router.get("/anomalies")
async def list_anomalies(
    service: FieldQualityServiceDep,
    status: Literal["open", "resolved", "ignored"] | None = Query(default=None),
    assignee: str | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
):
    """异常列表（默认返回 open，可按 status / assignee 筛选）"""
    rows = service.list_anomalies(status, limit, assignee)
    return {"items": rows, "total": len(rows)}
```

**4. Update `update_anomaly`** — support `assignee`:
```python
@router.put("/anomalies/{anomaly_id}")
async def update_anomaly(
    anomaly_id: str,
    body: AnomalyUpdateRequest,
    service: FieldQualityServiceDep,
):
    """标记异常状态或分配负责人"""
    service.update_anomaly(anomaly_id, status=body.status, assignee=body.assignee)
    new_status = body.status or "updated"
    return {"status": "updated", "id": anomaly_id, "new_status": new_status}
```

**5. Add new routes** (before the last route or after `trigger_check`):
```python
@router.get("/history", response_model=QualityHistoryResponse)
async def get_quality_history(
    service: FieldQualityServiceDep,
    days: int = Query(default=7, ge=3, le=90),
):
    """过去 N 天的质量趋势数据（默认 7 天）"""
    points = service.get_quality_history(days)
    current_score = service.get_summary().get("score_pct", 100)
    trend = service._compute_score_trend(date.today(), current_score)
    return QualityHistoryResponse(points=points, score_trend=trend)


@router.post("/send-digest", response_model=SendDigestResponse)
async def send_quality_digest(service: FieldQualityServiceDep):
    """手动触发质量摘要邮件/钉钉推送"""
    result = service.send_quality_digest()
    return SendDigestResponse(
        status="ok",
        email_sent=result["email_sent"],
        dingtalk_sent=result["dingtalk_sent"],
    )
```

**6. `list_anomalies` service method needs `assignee` param** — update `FieldQualityService.list_anomalies`:
```python
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
```

- [ ] **Step 1: Update `api/routes/quality.py`** — all route changes

- [ ] **Step 2: Commit**

```bash
git add api/routes/quality.py
git commit -m "feat(7B): add /history, /send-digest, ?assignee= filter to quality API"
```

---

## Task 6: Alert Config (Email + DingTalk)

**Files:**
- Modify: `api/config.py` — add `QualityEmailConfig`, `QualityDingTalkConfig`, wire into `AppConfig`
- Modify: `.env.example` — add new env vars

### Changes to `api/config.py`

Add new config classes (after `FeishuConfig`):
```python
class QualityEmailConfig(BaseSettings):
    """数据质量邮件告警配置"""

    model_config = SettingsConfigDict(
        env_prefix="quality_email_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    smtp_host: str = Field(default="smtp.example.com", description="SMTP 主机")
    smtp_port: int = Field(default=587, description="SMTP 端口")
    smtp_user: str = Field(default="", description="SMTP 用户名")
    smtp_password: str = Field(default="", description="SMTP 密码")
    from_addr: str = Field(default="finboss@example.com", description="发件人地址")
    to_addrs: list[str] = Field(default=[], description="收件人列表")

    @field_validator("to_addrs", mode="before")
    @classmethod
    def _parse_to_addrs(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v or []


class QualityDingTalkConfig(BaseSettings):
    """数据质量钉钉告警配置"""

    model_config = SettingsConfigDict(
        env_prefix="quality_dingtalk_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    webhook_url: str = Field(default="", description="钉钉自定义机器人 Webhook URL")


class QualityAlertConfig(BaseSettings):
    """数据质量告警总配置（聚合 Email + DingTalk）"""

    model_config = SettingsConfigDict(
        env_prefix="quality_alert_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    email_enabled: bool = Field(default=True, description="启用邮件告警")
    dingtalk_enabled: bool = Field(default=False, description="启用钉钉告警")
    digest_time: str = Field(default="07:00", description="每日摘要发送时间 (HH:MM)")
```

Add to `AppConfig` fields:
```python
    quality_email: QualityEmailConfig = Field(default_factory=QualityEmailConfig)
    quality_dingtalk: QualityDingTalkConfig = Field(default_factory=QualityDingTalkConfig)
    quality_alert: QualityAlertConfig = Field(default_factory=QualityAlertConfig)
```

### Changes to `.env.example`

Add at the end:
```bash
# Phase 7B — 数据质量告警
QUALITY_EMAIL_ENABLED=true
QUALITY_EMAIL_SMTP_HOST=smtp.example.com
QUALITY_EMAIL_SMTP_PORT=587
QUALITY_EMAIL_SMTP_USER=alerts@example.com
QUALITY_EMAIL_SMTP_PASSWORD=changeme
QUALITY_EMAIL_FROM_ADDR=finboss@example.com
QUALITY_EMAIL_TO_ADDRS=admin@example.com,ops@example.com

QUALITY_DINGTALK_ENABLED=false
QUALITY_DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxx

QUALITY_ALERT_DIGEST_TIME=07:00
```

- [ ] **Step 1: Update `api/config.py`** — add `QualityEmailConfig`, `QualityDingTalkConfig`, `QualityAlertConfig`

- [ ] **Step 2: Update `.env.example`** — add new env vars

- [ ] **Step 3: Commit**

```bash
git add api/config.py .env.example
git commit -m "feat(7B): add QualityEmailConfig, QualityDingTalkConfig, QualityAlertConfig"
```

---

## Task 7: HTML Report with Chart.js

**Files:**
- Modify: `templates/reports/quality_report.html.j2`

Replace the entire file with the new Chart.js version below. The template adds:
- Score trend line chart (last 14 days from history)
- Severity distribution pie chart
- Full anomaly table with assignee/SLA columns

```jinja2
{# templates/reports/quality_report.html.j2 #}
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>数据质量看板 - {{ stat_date }}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, sans-serif; background: #f5f7fa; padding: 20px; }
  .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; }
  .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
  h1 { font-size: 20px; }
  h2 { font-size: 15px; color: #2d3748; margin: 24px 0 12px; }
  .kpi-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 24px; }
  .kpi { background: #f8fafc; border-radius: 8px; padding: 14px; text-align: center; }
  .kpi .v { font-size: 20px; font-weight: 700; }
  .kpi .l { font-size: 11px; color: #718096; margin-top: 4px; }
  .kpi .v.danger { color: #e53e3e; }
  .kpi .v.warning { color: #d69e2e; }
  .kpi .v.success { color: #276749; }
  .score-bar { height: 6px; background: #e2e8f0; border-radius: 3px; margin-top: 8px; }
  .score-fill { height: 100%; border-radius: 3px; background: #48bb78; }
  .score-fill.danger { background: #e53e3e; }
  .score-fill.warning { background: #d69e2e; }
  .charts { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 24px; }
  .chart-box { background: #f8fafc; border-radius: 8px; padding: 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #f0f0f0; }
  th { color: #718096; font-size: 11px; text-transform: uppercase; background: #f7fafc; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; }
  .tag.high { background: #fed7d7; color: #c53030; }
  .tag.medium { background: #fefcbf; color: #975a16; }
  .tag.low { background: #c6f6d5; color: #276749; }
  .tag.overdue { background: #e53e3e; color: white; }
  .footer { margin-top: 24px; color: #a0aec0; font-size: 12px; text-align: center; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>数据质量看板</h1>
    <span style="color:#718096;">{{ stat_date }} | 自动扫描</span>
  </div>

  <div class="kpi-row">
    <div class="kpi">
      <div class="v">{{ summary.total_tables }}</div>
      <div class="l">监控表数</div>
    </div>
    <div class="kpi">
      <div class="v">{{ summary.total_fields }}</div>
      <div class="l">监控字段</div>
    </div>
    <div class="kpi">
      <div class="v{% if summary.anomaly_count > 0 %} danger{% endif %}">{{ summary.anomaly_count }}</div>
      <div class="l">异常数</div>
    </div>
    <div class="kpi">
      <div class="v{% if summary.high_severity > 0 %} danger{% elif summary.medium_severity > 0 %} warning{% endif %}">
        {{ summary.high_severity }} / {{ summary.medium_severity }}
      </div>
      <div class="l">高危 / 中危</div>
    </div>
    <div class="kpi">
      <div class="v{% if summary.score_pct < 90 %} danger{% elif summary.score_pct < 95 %} warning{% else %} success{% endif %}">
        {{ "%.1f"|format(summary.score_pct) }}%
      </div>
      <div class="l">健康度</div>
      <div class="score-bar">
        <div class="score-fill{% if summary.score_pct < 90 %} danger{% elif summary.score_pct < 95 %} warning{% endif %}"
             style="width:{{ summary.score_pct }}%"></div>
      </div>
    </div>
    <div class="kpi">
      <div class="v{% if summary.overdue_count > 0 %} danger{% endif %}">{{ summary.overdue_count }}</div>
      <div class="l">SLA 超时</div>
    </div>
  </div>

  <div class="charts">
    <div class="chart-box">
      <h2>评分趋势（近14天）</h2>
      <canvas id="trendChart" height="120"></canvas>
    </div>
    <div class="chart-box">
      <h2>严重程度分布</h2>
      <canvas id="pieChart" height="160"></canvas>
    </div>
  </div>

  <h2>异常字段明细</h2>
  <table>
    <thead>
      <tr>
        <th>表名</th>
        <th>字段</th>
        <th>指标</th>
        <th>当前值</th>
        <th>阈值</th>
        <th>级别</th>
        <th>状态</th>
        <th>负责人</th>
        <th>检测时间</th>
      </tr>
    </thead>
    <tbody>
    {% for a in anomalies %}
    <tr>
      <td>{{ a.table_name }}</td>
      <td>{{ a.column_name }}</td>
      <td>{{ a.metric }}</td>
      <td>{{ "%.4f"|format(a.value) }}</td>
      <td>{{ "%.4f"|format(a.threshold) }}</td>
      <td>
        <span class="tag {% if a.severity == '高' %}high{% elif a.severity == '中' %}medium{% else %}low{% endif %}">
          {{ a.severity }}
        </span>
      </td>
      <td>{{ a.status }}</td>
      <td>{{ a.assignee or '—' }}</td>
      <td>{{ a.detected_at }}</td>
    </tr>
    {% endfor %}
    {% if not anomalies %}
    <tr><td colspan="9" style="color:#718096;text-align:center;">✓ 无异常，数据质量良好</td></tr>
    {% endif %}
    </tbody>
  </table>

  <div class="footer">FinBoss 数据质量监控 | {{ generated_at }}</div>
</div>

<script>
const trendData = {{ trend_data | tojson }};
const severityData = {{ severity_data | tojson }};

const scoreColor = (score) => score < 90 ? 'rgba(229,62,62,0.8)' : score < 95 ? 'rgba(214,158,46,0.8)' : 'rgba(72,187,120,0.8)';

new Chart(document.getElementById('trendChart'), {
  type: 'line',
  data: {
    labels: trendData.map(p => p.stat_date),
    datasets: [{
      label: '健康度 (%)',
      data: trendData.map(p => p.score_pct),
      borderColor: 'rgba(66,153,225,0.8)',
      backgroundColor: 'rgba(66,153,225,0.1)',
      fill: true,
      tension: 0.3,
      pointBackgroundColor: trendData.map(p => scoreColor(p.score_pct)),
      pointRadius: 4,
    }]
  },
  options: {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: { y: { min: 0, max: 100, title: { display: true, text: '%' } } }
  }
});

new Chart(document.getElementById('pieChart'), {
  type: 'doughnut',
  data: {
    labels: ['高危', '中危', '低危'],
    datasets: [{
      data: [severityData.high, severityData.medium, severityData.low],
      backgroundColor: ['rgba(229,62,62,0.8)', 'rgba(214,158,46,0.8)', 'rgba(72,187,120,0.8)'],
    }]
  },
  options: {
    responsive: true,
    plugins: { legend: { position: 'bottom' } }
  }
});
</script>
</body>
</html>
```

### Update `generate_report_html` to pass chart data

In `services/field_quality_service.py`, update `generate_report_html` to pass trend/severity data:
```python
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
    # ... rest unchanged (write to static/reports/)
```

- [ ] **Step 1: Replace `templates/reports/quality_report.html.j2`** with new Chart.js version

- [ ] **Step 2: Update `generate_report_html()`** in `field_quality_service.py` to pass `trend_data` and `severity_data`

- [ ] **Step 3: Commit**

```bash
git add templates/reports/quality_report.html.j2
git commit -m "feat(7B): upgrade quality report with Chart.js trend + pie charts"
```

---

## Task 8: Scheduler — Daily Digest Job

**Files:**
- Modify: `services/scheduler_service.py`

### Change `_register_phase7a_jobs`

Add the daily digest job after the existing Phase 7A job:
```python
def _register_phase7a_jobs(scheduler: AsyncIOScheduler) -> None:
    # ... existing daily_quality_job ...

    def daily_quality_digest_job() -> None:
        """每日 07:00 发送质量摘要邮件/钉钉"""
        import logging
        logger8 = logging.getLogger(__name__)
        try:
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            result = svc.send_quality_digest()
            logger8.info(f"[Phase7B] Digest sent: email={result['email_sent']}, dingtalk={result['dingtalk_sent']}")
        except Exception as e:
            logger8.error(f"[Phase7B] Digest failed: {e}", exc_info=True)

    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        daily_quality_digest_job,
        CronTrigger(hour=7, minute=0),
        id="phase7b_quality_digest",
        name="数据质量每日摘要",
        replace_existing=True,
    )
```

Also update the log message at end of `start_scheduler` to include Phase 7B:
```python
    logger.info("Phase 5 + Phase 6 + Phase 7A + Phase 7B 调度任务已注册")
```

- [ ] **Step 1: Update `services/scheduler_service.py`** — add digest job

- [ ] **Step 2: Commit**

```bash
git add services/scheduler_service.py
git commit -m "feat(7B): add daily quality digest job (07:00 email + DingTalk)"
```

---

## Task 9: Tests

**Files:**
- Create: `tests/unit/test_quality_trend_sla.py`
- Modify: `tests/integration/test_quality_api.py`

### `tests/unit/test_quality_trend_sla.py`

```python
"""Phase 7B 趋势和 SLA 单元测试"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timedelta


class TestComputeScoreTrend:
    def test_improving_when_score_rising(self):
        with patch("services.field_quality_service.ClickHouseDataService") as MockCH:
            mock_ch = MagicMock()
            MockCH.return_value = mock_ch
            mock_ch.execute_query.return_value = [
                {"stat_date": date.today() - timedelta(days=2), "score": 70.0},
                {"stat_date": date.today() - timedelta(days=3), "score": 65.0},
            ]
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            result = svc._compute_score_trend(date.today(), current_score=80.0)
            assert result == "improving ↓"

    def test_degrading_when_score_falling(self):
        with patch("services.field_quality_service.ClickHouseDataService") as MockCH:
            mock_ch = MagicMock()
            MockCH.return_value = mock_ch
            mock_ch.execute_query.return_value = [
                {"stat_date": date.today() - timedelta(days=2), "score": 80.0},
                {"stat_date": date.today() - timedelta(days=3), "score": 85.0},
            ]
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            result = svc._compute_score_trend(date.today(), current_score=75.0)
            assert result == "degrading ↑"

    def test_stable_when_insufficient_history(self):
        with patch("services.field_quality_service.ClickHouseDataService") as MockCH:
            mock_ch = MagicMock()
            MockCH.return_value = mock_ch
            mock_ch.execute_query.return_value = []
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            result = svc._compute_score_trend(date.today(), current_score=80.0)
            assert result == "stable →"


class TestOverdueAnomalies:
    def test_count_overdue_high_severity(self):
        with patch("services.field_quality_service.ClickHouseDataService") as MockCH:
            mock_ch = MagicMock()
            MockCH.return_value = mock_ch
            mock_ch.execute_query.return_value = [{"cnt": 2}]
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            count = svc._count_overdue_anomalies(date.today())
            assert count == 2

    def test_zero_when_no_overdue(self):
        with patch("services.field_quality_service.ClickHouseDataService") as MockCH:
            mock_ch = MagicMock()
            MockCH.return_value = mock_ch
            mock_ch.execute_query.return_value = [{"cnt": 0}]
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            count = svc._count_overdue_anomalies(date.today())
            assert count == 0


class TestUpdateAnomalyAssignee:
    def test_update_assignee_only(self):
        with patch("services.field_quality_service.ClickHouseDataService") as MockCH:
            mock_ch = MagicMock()
            MockCH.return_value = mock_ch
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            svc.update_anomaly("a1", assignee="zhangsan")
            mock_ch.execute.assert_called_once()
            call_sql = mock_ch.execute.call_args[0][0]
            assert "assignee = 'zhangsan'" in call_sql
            assert "status =" not in call_sql

    def test_update_both_status_and_assignee(self):
        with patch("services.field_quality_service.ClickHouseDataService") as MockCH:
            mock_ch = MagicMock()
            MockCH.return_value = mock_ch
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            svc.update_anomaly("a1", status="resolved", assignee="lisi")
            mock_ch.execute.assert_called_once()
            call_sql = mock_ch.execute.call_args[0][0]
            assert "status = 'resolved'" in call_sql
            assert "assignee = 'lisi'" in call_sql


class TestQualityHistory:
    def test_history_returns_ordered_points(self):
        with patch("services.field_quality_service.ClickHouseDataService") as MockCH:
            mock_ch = MagicMock()
            MockCH.return_value = mock_ch
            mock_ch.execute_query.side_effect = [
                [{"stat_date": date.today(), "score_pct": 80.0, "anomaly_count": 5}],
                [{"severity": "高", "cnt": 2}, {"severity": "中", "cnt": 3}],
            ]
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            result = svc.get_quality_history(days=7)
            assert len(result) == 1
            assert result[0]["score_pct"] == 80.0
            assert result[0]["high_severity"] == 2
            assert result[0]["medium_severity"] == 3
```

### `tests/integration/test_quality_api.py` additions

Add these tests to `TestQualityAPI` class:
```python
def test_get_summary_includes_trend_and_overdue(self, client):
    with patch("services.field_quality_service.FieldQualityService.get_summary") as mock:
        mock.return_value = {
            "stat_date": "2026-03-22",
            "total_tables": 3,
            "total_fields": 20,
            "anomaly_count": 2,
            "high_severity": 1,
            "medium_severity": 1,
            "score_pct": 90.0,
            "score_trend": "improving ↓",
            "overdue_count": 0,
            "last_check_at": "2026-03-22T06:00:00",
        }
        resp = client.get("/api/v1/quality/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["score_trend"] == "improving ↓"
        assert data["overdue_count"] == 0

def test_list_anomalies_by_assignee(self, client):
    with patch("services.field_quality_service.FieldQualityService.list_anomalies") as mock:
        mock.return_value = [
            {
                "id": "a1",
                "table_name": "dm.ar",
                "column_name": "due_date",
                "metric": "null_rate",
                "value": 0.35,
                "threshold": 0.20,
                "severity": "高",
                "status": "open",
                "assignee": "zhangsan",
                "detected_at": "2026-03-22T06:00:00",
            }
        ]
        resp = client.get("/api/v1/quality/anomalies?assignee=zhangsan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["assignee"] == "zhangsan"
        mock.assert_called_once_with("open", 100, "zhangsan")

def test_update_anomaly_assignee(self, client):
    with patch("services.field_quality_service.FieldQualityService.update_anomaly") as mock:
        mock.return_value = None
        resp = client.put(
            "/api/v1/quality/anomalies/a1",
            json={"assignee": "lisi", "note": "assigned"},
        )
        assert resp.status_code == 200
        mock.assert_called_once_with("a1", status=None, assignee="lisi")

def test_get_quality_history(self, client):
    with patch("services.field_quality_service.FieldQualityService.get_quality_history") as mock_hist, \
         patch("services.field_quality_service.FieldQualityService.get_summary") as mock_sum:
        mock_hist.return_value = [
            {"stat_date": "2026-03-22", "score_pct": 90.0, "anomaly_count": 2,
             "high_severity": 0, "medium_severity": 2},
            {"stat_date": "2026-03-21", "score_pct": 85.0, "anomaly_count": 5,
             "high_severity": 1, "medium_severity": 4},
        ]
        mock_sum.return_value = {"score_pct": 90.0}
        resp = client.get("/api/v1/quality/history?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert data["score_trend"] == "stable →"
        assert len(data["points"]) == 2

def test_send_digest(self, client):
    with patch("services.field_quality_service.FieldQualityService.send_quality_digest") as mock:
        mock.return_value = {"email_sent": 2, "dingtalk_sent": 1}
        resp = client.post("/api/v1/quality/send-digest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email_sent"] == 2
        assert data["dingtalk_sent"] == 1
```

- [ ] **Step 1: Write `tests/unit/test_quality_trend_sla.py`**

- [ ] **Step 2: Add integration tests to `tests/integration/test_quality_api.py`**

- [ ] **Step 3: Run all Phase 7B tests**

Run: `uv run pytest tests/unit/test_quality_trend_sla.py tests/integration/test_quality_api.py -v 2>&1 | tail -30`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_quality_trend_sla.py tests/integration/test_quality_api.py
git commit -m "test(7B): add trend/SLA and API integration tests"
```

---

## Summary

After all 9 tasks:
- 374 → 385+ tests passing
- DDL applied to ClickHouse
- All Phase 7B features delivered: trend API, SLA tracking, assignee, email + DingTalk alerts, Chart.js HTML dashboard
