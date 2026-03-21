# Phase 7A - 数据质量监控面板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-discover all ClickHouse dm/std/raw tables, compute per-column quality metrics (null_rate, distinct_rate, negative_rate, freshness_hours), persist anomalies to ClickHouse, render an HTML dashboard, send Feishu card, and expose a REST API.

**Architecture:** Phase 7A introduces a new `FieldQualityService` class (not extending the Phase 1 in-memory `QualityService` — concerns are completely different). The scheduler calls `FieldQualityService.check_all()` daily at 06:00. Existing `QualityService` is untouched.

**Tech Stack:** ClickHouse SQL aggregation, Jinja2 HTML, APScheduler, FeishuClient, Pydantic schemas.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/phase7a_ddl.sql` | Create | `dm.quality_reports` + `dm.quality_anomalies` tables |
| `scripts/init_phase7a.py` | Create | Run DDL, register with Phase 1 init if needed |
| `schemas/quality.py` | Create | Pydantic models: `QualityReport`, `QualityAnomaly`, `Severity` |
| `services/field_quality_service.py` | Create | Table discovery + per-column metric SQL + anomaly detection |
| `api/routes/quality.py` | Create | All 6 REST endpoints |
| `api/dependencies.py` | Modify | Add `FieldQualityServiceDep` |
| `api/main.py` | Modify | Register `quality` router |
| `services/scheduler_service.py` | Modify | Add `phase7a_daily_quality` APScheduler job |
| `templates/reports/quality_report.html.j2` | Create | HTML dashboard |
| `tests/unit/test_field_quality_service.py` | Create | Unit tests |
| `tests/integration/test_quality_api.py` | Create | Integration tests |

---

## Task 1: DDL + Init Script

**Files:**
- Create: `scripts/phase7a_ddl.sql`
- Create: `scripts/init_phase7a.py`
- Modify: `scripts/init_phase5.py` (add Phase 7A to `--phases` CLI if not already all-run)

- [ ] **Step 1: Write DDL**

```sql
-- scripts/phase7a_ddl.sql

CREATE TABLE IF NOT EXISTS dm.quality_reports (
    id              String,
    stat_date       Date,
    table_name      String,
    total_fields    UInt32,
    anomaly_count   UInt32,
    score_pct       Float64,
    generated_at    DateTime,
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(generated_at)
ORDER BY (stat_date, table_name)
SETTINGS allow_experimental_object_type = 1;

CREATE TABLE IF NOT EXISTS dm.quality_anomalies (
    id              String,
    report_id       String,
    stat_date       Date,
    table_name      String,
    column_name     String,
    metric          String,
    value           Float64,
    threshold       Float64,
    severity        String,
    status          String DEFAULT 'open',
    detected_at     DateTime,
    resolved_at     DateTime DEFAULT toDateTime('1970-01-01 00:00:00'),
    PRIMARY KEY (id)
) ENGINE = ReplacingMergeTree(detected_at)
ORDER BY (stat_date, table_name, column_name, metric)
SETTINGS allow_experimental_object_type = 1;
```

- [ ] **Step 2: Write init script**

```python
# scripts/init_phase7a.py
"""Phase 7A DDL initialization script"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.clickhouse_service import ClickHouseDataService
from scripts.phase7a_ddl import DDL_STATEMENTS  # embed SQL as string constant


def init_phase7a() -> None:
    ch = ClickHouseDataService()
    for stmt in DDL_STATEMENTS:
        try:
            ch.execute(stmt)
            print(f"OK: {stmt[:60]}")
        except Exception as e:
            if "already exists" in str(e).lower() or "code: 57" in str(e):
                print(f"SKIP (exists): {stmt[:60]}")
            else:
                raise
    print("Phase 7A DDL done.")


if __name__ == "__main__":
    init_phase7a()
```

- [ ] **Step 3: Run init script**

Run: `uv run python scripts/init_phase7a.py`
Expected: `Phase 7A DDL done.`

- [ ] **Step 4: Commit**

```bash
git add scripts/phase7a_ddl.sql scripts/init_phase7a.py
git commit -m "feat: Phase 7A DDL + init script (quality_reports, quality_anomalies)"
```

---

## Task 2: Pydantic Schemas

**Files:**
- Create: `schemas/quality.py`
- Create: `api/schemas/quality.py`

- [ ] **Step 1: Write core Pydantic models**

```python
# schemas/quality.py
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class AnomalyStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class QualityMetric(str, Enum):
    NULL_RATE = "null_rate"
    DISTINCT_RATE = "distinct_rate"
    NEGATIVE_RATE = "negative_rate"
    FRESHNESS_HOURS = "freshness_hours"


class QualityAnomaly(BaseModel):
    id: str
    report_id: str
    stat_date: date
    table_name: str
    column_name: str
    metric: QualityMetric
    value: float
    threshold: float
    severity: Severity
    status: AnomalyStatus = AnomalyStatus.OPEN
    detected_at: datetime
    resolved_at: datetime | None = None


class QualityReport(BaseModel):
    id: str
    stat_date: date
    table_name: str
    total_fields: int
    anomaly_count: int
    score_pct: float
    generated_at: datetime
```

- [ ] **Step 2: Write API request/response schemas**

```python
# api/schemas/quality.py
from datetime import date, datetime

from pydantic import BaseModel

from schemas.quality import AnomalyStatus, Severity


class QualitySummaryResponse(BaseModel):
    stat_date: date
    total_tables: int
    total_fields: int
    anomaly_count: int
    high_severity: int
    medium_severity: int
    score_pct: float
    last_check_at: datetime | None


class AnomalyUpdateRequest(BaseModel):
    status: Literal["resolved", "ignored"]
    note: str | None = None


class CheckResponse(BaseModel):
    status: str
    report_count: int
    anomaly_count: int
    duration_ms: int
```

- [ ] **Step 3: Commit**

```bash
git add schemas/quality.py api/schemas/quality.py
git commit -m "feat: Phase 7A Pydantic schemas (quality)"
```

---

## Task 3: FieldQualityService

**Files:**
- Create: `services/field_quality_service.py`
- Test: `tests/unit/test_field_quality_service.py`

- [ ] **Step 1: Write unit tests first**

```python
# tests/unit/test_field_quality_service.py
import pytest
from unittest.mock import MagicMock
from datetime import date
from services.field_quality_service import FieldQualityService


class TestFieldQualityService:
    def test_list_monitored_tables(self):
        mock_ch = MagicMock()
        mock_ch.execute_query.return_value = [
            {"database": "dm", "name": "customer360"},
            {"database": "std", "name": "ar_record"},
        ]
        svc = FieldQualityService(ch=mock_ch)
        tables = svc.list_monitored_tables()
        assert tables == ["dm.customer360", "std.ar_record"]

    def test_compute_null_rate_anomaly(self):
        mock_ch = MagicMock()
        mock_ch.execute_query.return_value = [
            {"column_name": "due_date", "null_rate": 0.35, "type": "Nullable(Date)"}
        ]
        svc = FieldQualityService(ch=mock_ch)
        anomalies = svc.check_column("dm.ar", "due_date", date.today())
        assert len(anomalies) == 1
        assert anomalies[0].severity == "高"
        assert anomalies[0].metric == "null_rate"
        assert anomalies[0].value == 0.35

    def test_no_anomaly_when_under_threshold(self):
        mock_ch = MagicMock()
        mock_ch.execute_query.return_value = [
            {"column_name": "amount", "null_rate": 0.01, "type": "Decimal(18,2)"}
        ]
        svc = FieldQualityService(ch=mock_ch)
        anomalies = svc.check_column("dm.ar", "amount", date.today())
        assert anomalies == []

    def test_negative_rate_numeric_only(self):
        mock_ch = MagicMock()
        mock_ch.execute_query.return_value = [
            {"column_name": "amount", "null_rate": 0.0, "type": "Decimal(18,2)"},
            {"column_name": "name", "null_rate": 0.0, "type": "String"},
        ]
        svc = FieldQualityService(ch=mock_ch)
        # String field should not be checked for negative_rate
        result = svc._should_check_negative_rate("String")
        assert result is False
        result = svc._should_check_negative_rate("Decimal(18,2)")
        assert result is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_field_quality_service.py -v`
Expected: FAIL — `FieldQualityService` not defined

- [ ] **Step 3: Write FieldQualityService skeleton**

```python
# services/field_quality_service.py
"""字段级数据质量检查服务"""
import logging
import uuid
from datetime import date, datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader

from services.clickhouse_service import ClickHouseDataService

PROJECT_ROOT = __file__.rsplit("/", 2)[0]


class FieldQualityService:
    """字段级数据质量检查"""

    THRESHOLDS = {
        "null_rate":        {"high": 0.20, "medium": 0.10},
        "distinct_rate":    {"high": 0.999, "medium": 0.99},
        "negative_rate":    {"high": 0.05, "medium": 0.02},
        "freshness_hours":  {"high": 72, "medium": 48},
    }

    def __init__(
        self,
        ch: ClickHouseDataService | None = None,
    ):
        self._ch = ch or ClickHouseDataService()
        self._jinja = Environment(
            loader=FileSystemLoader(PROJECT_ROOT / "templates" / "reports"),
            autoescape=True,
        )

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
        rows = self._ch.execute_query(
            f"SELECT column_name, type FROM system.columns "
            f"WHERE database = '{db}' AND table = '{name}' "
            f"ORDER BY position"
        )
        return rows

    def check_column(
        self,
        table_name: str,
        column_name: str,
        stat_date: date,
    ) -> list[dict[str, Any]]:
        """检查单个字段，返回异常列表（空列表=正常）"""
        cols = self.list_columns(table_name)
        col_info = next((c for c in cols if c["column_name"] == column_name), None)
        if not col_info:
            return []
        col_type = col_info["type"]

        anomalies = []
        today_str = stat_date.isoformat()
        escaped_col = column_name  # column names are safe identifiers

        # null_rate — all types
        null_rows = self._ch.execute_query(
            f"SELECT countIf(`{escaped_col}` IS NULL) / count() AS null_rate "
            f"FROM {table_name} WHERE toDate(etl_time) = '{today_str}'"
        )
        null_rate = float(null_rows[0]["null_rate"]) if null_rows else 0.0
        t = self.THRESHOLDS["null_rate"]
        if null_rate > t["high"]:
            anomalies.append(self._make_anomaly(table_name, column_name, "null_rate", null_rate, t["high"], "高"))
        elif null_rate > t["medium"]:
            anomalies.append(self._make_anomaly(table_name, column_name, "null_rate", null_rate, t["medium"], "中"))

        # distinct_rate — all types
        distinct_rows = self._ch.execute_query(
            f"SELECT uniqExact(`{escaped_col}`) / count() AS distinct_rate "
            f"FROM {table_name} WHERE toDate(etl_time) = '{today_str}'"
        )
        distinct_rate = float(distinct_rows[0]["distinct_rate"]) if distinct_rows else 0.0
        t = self.THRESHOLDS["distinct_rate"]
        if distinct_rate > t["high"]:
            anomalies.append(self._make_anomaly(table_name, column_name, "distinct_rate", distinct_rate, t["high"], "中"))
        elif distinct_rate > t["medium"]:
            anomalies.append(self._make_anomaly(table_name, column_name, "distinct_rate", distinct_rate, t["medium"], "低"))

        # negative_rate — numeric types only
        if self._should_check_negative_rate(col_type):
            neg_rows = self._ch.execute_query(
                f"SELECT countIf(`{escaped_col}` < 0) / count() AS negative_rate "
                f"FROM {table_name} WHERE toDate(etl_time) = '{today_str}'"
            )
            negative_rate = float(neg_rows[0]["negative_rate"]) if neg_rows else 0.0
            t = self.THRESHOLDS["negative_rate"]
            if negative_rate > t["high"]:
                anomalies.append(self._make_anomaly(table_name, column_name, "negative_rate", negative_rate, t["high"], "高"))
            elif negative_rate > t["medium"]:
                anomalies.append(self._make_anomaly(table_name, column_name, "negative_rate", negative_rate, t["medium"], "中"))

        return anomalies

    def check_all(self, stat_date: date | None = None) -> dict[str, Any]:
        """对所有表执行字段级质量检查"""
        stat_date = stat_date or date.today()
        today_str = stat_date.isoformat()
        report_id = str(uuid.uuid4())
        now_str = datetime.now().isoformat()

        tables = self.list_monitored_tables()
        total_fields = 0
        all_anomalies = []
        table_scores = []

        for table_name in tables:
            cols = self.list_columns(table_name)
            normal_count = 0
            table_anomalies = []
            for col in cols:
                col_anomalies = self.check_column(table_name, col["column_name"], stat_date)
                total_fields += 1
                if col_anomalies:
                    table_anomalies.extend(col_anomalies)
                else:
                    normal_count += 1
            all_anomalies.extend(table_anomalies)
            score_pct = (normal_count / len(cols) * 100) if cols else 100.0
            table_scores.append(score_pct)

            # save report row
            self._ch.execute(
                f"INSERT INTO dm.quality_reports "
                f"(id, stat_date, table_name, total_fields, anomaly_count, score_pct, generated_at) "
                f"VALUES ('{report_id}', '{today_str}', '{table_name}', {len(cols)}, "
                f"{len(table_anomalies)}, {score_pct:.2f}, '{now_str}')"
            )

        # save anomalies
        for a in all_anomalies:
            resolved_at = "toDateTime('1970-01-01 00:00:00')"
            self._ch.execute(
                f"INSERT INTO dm.quality_anomalies "
                f"(id, report_id, stat_date, table_name, column_name, metric, value, threshold, severity, status, detected_at, resolved_at) "
                f"VALUES ('{a['id']}', '{report_id}', '{today_str}', '{a['table_name']}', '{a['column_name']}', "
                f"'{a['metric']}', {a['value']:.6f}, {a['threshold']:.6f}, '{a['severity']}', 'open', '{now_str}', {resolved_at})"
            )

        overall_score = sum(table_scores) / len(table_scores) if table_scores else 100.0
        return {
            "report_id": report_id,
            "stat_date": today_str,
            "total_tables": len(tables),
            "total_fields": total_fields,
            "anomaly_count": len(all_anomalies),
            "score_pct": round(overall_score, 2),
        }

    def _should_check_negative_rate(self, col_type: str) -> bool:
        numeric_prefixes = ("Int", "UInt", "Float", "Decimal")
        return any(col_type.startswith(p) for p in numeric_prefixes)

    def _make_anomaly(
        self,
        table_name: str,
        column_name: str,
        metric: str,
        value: float,
        threshold: float,
        severity: str,
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

    def list_open_anomalies(self, limit: int = 100) -> list[dict]:
        return self._ch.execute_query(
            f"SELECT * FROM dm.quality_anomalies "
            f"WHERE status = 'open' "
            f"ORDER BY severity DESC, detected_at DESC "
            f"LIMIT {limit}"
        )

    def update_anomaly(self, anomaly_id: str, status: str) -> None:
        now_str = datetime.now().isoformat()
        resolved_at = f"'{now_str}'" if status in ("resolved", "ignored") else "toDateTime('1970-01-01 00:00:00')"
        self._ch.execute(
            f"ALTER TABLE dm.quality_anomalies UPDATE status = '{status}', resolved_at = {resolved_at} "
            f"WHERE id = '{anomaly_id}'"
        )

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
        date_str = stat_date.isoformat() if stat_date else date.today().isoformat()
        anomalies = self.list_open_anomalies(limit=10)

        high = [a for a in anomalies if a["severity"] == "高"]
        medium = [a for a in anomalies if a["severity"] == "中"]

        card = {
            "header": {
                "title": {"tag": "plain_text", "content": f"🚨 数据质量日报 - {date_str}"},
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
                f"- `{a['table_name']}.{a['column_name']}` — {a['metric']} {a['value']:.1%}（阈值 {a['threshold']:.1%}）"
                for a in high
            )
            card["elements"].append({"tag": "markdown", "content": f"**高危（{len(high)}）**\n{lines}"})
        if medium:
            lines = "\n".join(
                f"- `{a['table_name']}.{a['column_name']}` — {a['metric']} {a['value']:.1%}（阈值 {a['threshold']:.1%}）"
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_field_quality_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/field_quality_service.py tests/unit/test_field_quality_service.py
git commit -m "feat: Phase 7A FieldQualityService with column-level metric checks"
```

---

## Task 4: Quality Report HTML Template

**Files:**
- Create: `templates/reports/quality_report.html.j2`

- [ ] **Step 1: Write template**

```html
{# templates/reports/quality_report.html.j2 #}
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>数据质量看板 - {{ stat_date }}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, sans-serif; background: #f5f7fa; padding: 20px; }
  .container { max-width: 1100px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; }
  .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
  h1 { font-size: 20px; }
  .kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 24px; }
  .kpi { background: #f8fafc; border-radius: 8px; padding: 16px; text-align: center; }
  .kpi .v { font-size: 22px; font-weight: 700; }
  .kpi .l { font-size: 12px; color: #888; margin-top: 4px; }
  .kpi .v.danger { color: #e53e3e; }
  .kpi .v.warning { color: #d69e2e; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 16px; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }
  th { color: #888; font-size: 12px; text-transform: uppercase; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
  .tag.high { background: #fed7d7; color: #c53030; }
  .tag.medium { background: #fefcbf; color: #975a16; }
  .tag.low { background: #c6f6d5; color: #276749; }
  .score-bar { height: 8px; background: #e2e8f0; border-radius: 4px; margin-top: 8px; }
  .score-fill { height: 100%; border-radius: 4px; background: #48bb78; }
  .score-fill.danger { background: #e53e3e; }
  .score-fill.warning { background: #d69e2e; }
  .footer { margin-top: 24px; color: #aaa; font-size: 12px; text-align: center; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>数据质量看板</h1>
    <span style="color:#888;">{{ stat_date }} | 自动扫描</span>
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
      <div class="v danger">{{ summary.anomaly_count }}</div>
      <div class="l">异常数</div>
    </div>
    <div class="kpi">
      <div class="v {% if summary.high_severity > 0 %}danger{% elif summary.medium_severity > 0 %}warning{% endif %}">
        {{ summary.high_severity }} / {{ summary.medium_severity }}
      </div>
      <div class="l">高危 / 中危</div>
    </div>
    <div class="kpi">
      <div class="v {% if summary.score_pct < 90 %}danger{% elif summary.score_pct < 95 %}warning{% endif %}">
        {{ "%.1f"|format(summary.score_pct) }}%
      </div>
      <div class="l">健康度</div>
      <div class="score-bar">
        <div class="score-fill {% if summary.score_pct < 90 %}danger{% elif summary.score_pct < 95 %}warning{% endif %}"
             style="width:{{ summary.score_pct }}%"></div>
      </div>
    </div>
  </div>

  <h2 style="font-size:15px;margin-bottom:8px;">异常字段明细</h2>
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
      </tr>
    </thead>
    <tbody>
    {% for a in anomalies %}
    <tr>
      <td>{{ a.table_name }}</td>
      <td>{{ a.column_name }}</td>
      <td>{{ a.metric }}</td>
      <td>{{ "%.2f"|format(a.value) }}</td>
      <td>{{ "%.2f"|format(a.threshold) }}</td>
      <td>
        <span class="tag {% if a.severity == '高' %}high{% elif a.severity == '中' %}medium{% else %}low{% endif %}">
          {{ a.severity }}
        </span>
      </td>
      <td>{{ a.status }}</td>
    </tr>
    {% endfor %}
    {% if not anomalies %}
    <tr><td colspan="7" style="color:#888;text-align:center;">✓ 无异常，数据质量良好</td></tr>
    {% endif %}
    </tbody>
  </table>

  <div class="footer">FinBoss 数据质量监控 | {{ generated_at }}</div>
</div>
</body>
</html>
```

- [ ] **Step 2: Write `generate_report_html` method in FieldQualityService**

Add to `FieldQualityService` in `services/field_quality_service.py`:

```python
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
    filename = f"quality_report_{stat_date.isoformat()}.html"
    (output_dir / filename).write_text(html, encoding="utf-8")
    return str(output_dir / filename)
```

- [ ] **Step 3: Commit**

```bash
git add templates/reports/quality_report.html.j2
git commit -m "feat: Phase 7A quality report HTML template"
```

---

## Task 5: Quality API Routes

**Files:**
- Create: `api/routes/quality.py`
- Modify: `api/dependencies.py` (add FieldQualityServiceDep)
- Modify: `api/main.py` (register router)

- [ ] **Step 1: Write API routes**

```python
# api/routes/quality.py
"""数据质量 API 路由"""
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import FieldQualityServiceDep
from api.schemas.quality import AnomalyUpdateRequest, CheckResponse, QualitySummaryResponse
from services.field_quality_service import FieldQualityService

router = APIRouter(tags=["quality"])


@router.get("/summary", response_model=QualitySummaryResponse)
async def get_quality_summary(service: FieldQualityServiceDep):
    """全局健康度概览"""
    return service.get_summary()


@router.get("/reports")
async def list_reports(
    service: FieldQualityServiceDep,
    stat_date: date | None = Query(default=None),
    limit: int = Query(default=50, le=500),
):
    """质量报告列表"""
    date_str = stat_date.isoformat() if stat_date else date.today().isoformat()
    rows = service._ch.execute_query(
        f"SELECT * FROM dm.quality_reports "
        f"WHERE stat_date = '{date_str}' "
        f"ORDER BY generated_at DESC LIMIT {limit}"
    )
    return {"items": rows, "total": len(rows)}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, service: FieldQualityServiceDep):
    """报告详情（含异常明细）"""
    report_rows = service._ch.execute_query(
        f"SELECT * FROM dm.quality_reports WHERE id = '{report_id}' LIMIT 1"
    )
    if not report_rows:
        raise HTTPException(status_code=404, detail="Report not found")
    anomaly_rows = service._ch.execute_query(
        f"SELECT * FROM dm.quality_anomalies "
        f"WHERE report_id = '{report_id}' "
        f"ORDER BY severity DESC, detected_at DESC"
    )
    return {"report": report_rows[0], "anomalies": anomaly_rows}


@router.get("/anomalies")
async def list_anomalies(
    service: FieldQualityServiceDep,
    status: Literal["open", "resolved", "ignored"] | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
):
    """当前异常列表"""
    where = f"status = '{status}'" if status else "status = 'open'"
    rows = service._ch.execute_query(
        f"SELECT * FROM dm.quality_anomalies "
        f"WHERE {where} "
        f"ORDER BY severity DESC, detected_at DESC LIMIT {limit}"
    )
    return {"items": rows, "total": len(rows)}


@router.put("/anomalies/{anomaly_id}")
async def update_anomaly(
    anomaly_id: str,
    body: AnomalyUpdateRequest,
    service: FieldQualityServiceDep,
):
    """标记异常为已处理/忽略"""
    service.update_anomaly(anomaly_id, body.status)
    return {"status": "updated", "id": anomaly_id, "new_status": body.status}


@router.post("/check", response_model=CheckResponse)
async def trigger_check(service: FieldQualityServiceDep):
    """手动触发一次质量检查"""
    import time
    start = time.monotonic()
    result = service.check_all()
    service.send_feishu_card()
    duration_ms = int((time.monotonic() - start) * 1000)
    return CheckResponse(
        status="ok",
        report_count=result["total_tables"],
        anomaly_count=result["anomaly_count"],
        duration_ms=duration_ms,
    )
```

- [ ] **Step 2: Add dependency**

In `api/dependencies.py`, add:

```python
from services.field_quality_service import FieldQualityService

@lru_cache
def get_field_quality_service() -> FieldQualityService:
    return FieldQualityService()

FieldQualityServiceDep = Annotated[FieldQualityService, Depends(get_field_quality_service)]
```

- [ ] **Step 3: Register router**

In `api/main.py`, add:

```python
from api.routes import quality

app.include_router(quality.router, prefix="/api/v1/quality", dependencies=[Depends(get_field_quality_service)])
```

- [ ] **Step 4: Commit**

```bash
git add api/routes/quality.py api/dependencies.py api/main.py
git commit -m "feat: Phase 7A Quality API routes"
```

---

## Task 6: APScheduler Integration

**Files:**
- Modify: `services/scheduler_service.py`

- [ ] **Step 1: Add Phase 7A job to scheduler**

Add to `services/scheduler_service.py`:

```python
def _register_phase7a_jobs(scheduler: AsyncIOScheduler) -> None:
    """注册 Phase 7A 调度任务：每日 06:00 数据质量检查"""

    def daily_quality_job() -> None:
        import logging
        logger4 = logging.getLogger(__name__)
        try:
            from services.field_quality_service import FieldQualityService
            svc = FieldQualityService()
            result = svc.check_all()
            svc.send_feishu_card()
            svc.generate_report_html()
            logger4.info(f"[Phase7A] Quality check done: {result['total_tables']} tables, {result['anomaly_count']} anomalies")
        except Exception as e:
            logger4.error(f"[Phase7A] Quality check failed: {e}", exc_info=True)

    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        daily_quality_job,
        CronTrigger(hour=6, minute=0),
        id="phase7a_daily_quality",
        name="数据质量每日检查",
        replace_existing=True,
    )
```

In `start_scheduler()`, after `_register_phase6_jobs(_scheduler)` add:
```python
_register_phase7a_jobs(_scheduler)
```

- [ ] **Step 2: Commit**

```bash
git add services/scheduler_service.py
git commit -m "feat: Phase 7A APScheduler daily quality check at 06:00"
```

---

## Task 7: Integration Tests

**Files:**
- Create: `tests/integration/test_quality_api.py`

- [ ] **Step 1: Write integration tests**

```python
# tests/integration/test_quality_api.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import date


class TestQualityAPI:
    def test_get_summary(self, client):
        with patch("services.field_quality_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [{
                "total_tables": 3,
                "total_fields": 20,
                "anomaly_count": 2,
                "score_pct": 90.0,
                "last_check_at": "2026-03-21T06:00:00",
            }]
            resp = client.get("/api/v1/quality/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_tables"] == 3
            assert data["anomaly_count"] == 2

    def test_trigger_check(self, client):
        with patch("services.field_quality_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.side_effect = [
                # list tables
                [{"database": "dm", "name": "ar"}],
                # columns
                [{"column_name": "amount", "type": "Decimal(18,2)"}],
                # null_rate query
                [{"null_rate": 0.01}],
                # distinct_rate query
                [{"distinct_rate": 0.5}],
                # negative_rate query
                [{"negative_rate": 0.0}],
            ]
            mock_ch.execute.return_value = None
            resp = client.post("/api/v1/quality/check")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "duration_ms" in data

    def test_list_anomalies(self, client):
        with patch("services.field_quality_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [
                {
                    "id": "a1",
                    "table_name": "dm.ar",
                    "column_name": "due_date",
                    "metric": "null_rate",
                    "value": 0.35,
                    "threshold": 0.20,
                    "severity": "高",
                    "status": "open",
                    "detected_at": "2026-03-21T06:00:00",
                }
            ]
            resp = client.get("/api/v1/quality/anomalies")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["items"][0]["severity"] == "高"

    def test_update_anomaly_resolved(self, client):
        with patch("services.field_quality_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute.return_value = None
            resp = client.put(
                "/api/v1/quality/anomalies/a1",
                json={"status": "resolved", "note": "fixed"},
            )
            assert resp.status_code == 200
            assert resp.json()["new_status"] == "resolved"
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_quality_api.py -v`
Expected: PASS

- [ ] **Step 3: Run full suite**

Run: `uv run pytest tests/ -v --tb=short 2>&1 | tail -10`
Expected: all pass, no regressions

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_quality_api.py
git commit -m "test: Phase 7A integration tests for Quality API"
```
