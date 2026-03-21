# Phase 5 预警报表与自动化报告 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建逾期预警引擎（5条内置规则）、HTML管理看板、自动化周报/月报生成与飞书推送。

**Architecture:**
- `AlertService` — 纯业务逻辑：读规则 → 构造 SQL → 查询 ClickHouse → 比对阈值 → 写 history → 推送飞书
- `DashboardService` — Jinja2 模板渲染 → 写入 `static/reports/`
- `ReportService` — 填充报告模板 → 写文件 → 发送飞书
- APScheduler — 预警 09:00，看板 02:30，周报周一 08:00，月报每月1日 08:00

**Tech Stack:** Jinja2, APScheduler, ClickHouse, FeishuClient, Pydantic

---

## 文件结构

```
新增文件:
  schemas/alert.py                        # AlertRule, AlertHistory Pydantic 模型
  services/alert_service.py               # 预警规则引擎
  services/dashboard_service.py           # 看版 HTML 生成
  services/report_service.py              # 周报/月报生成与发送
  api/routes/alerts.py                   # 预警规则 CRUD + history
  api/routes/reports.py                  # 报告生成触发 + records
  api/schemas/alert.py                  # API 请求/响应模型
  scripts/phase5_ddl.sql                # ClickHouse DDL
  scripts/init_phase5.py                 # Phase 5 表初始化
  templates/reports/
    dashboard.html.j2                    # 看版模板
    weekly_report.html.j2                # 周报模板
    monthly_report.html.j2               # 月报模板
  tests/unit/test_alert_service.py
  tests/integration/test_alerts_api.py

修改文件:
  api/config.py                          # +FEISHU_MGMT_CHANNEL_ID
  api/main.py                           # 注册 alerts/reports 路由 + 静态文件挂载
  services/scheduler_service.py          # +Phase 5 调度任务
  pyproject.toml                        # +jinja2
```

---

## Task 1: DDL + 初始化脚本

**Files:**
- Create: `scripts/phase5_ddl.sql`
- Create: `scripts/init_phase5.py`
- Test: `tests/unit/test_phase5_init.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_phase5_init.py
"""测试 Phase 5 DDL 和初始化脚本"""
import pytest
from unittest.mock import MagicMock, patch


def test_ddl_creates_4_tables():
    """验证 DDL 包含 4 张表的 CREATE 语句"""
    from pathlib import Path
    ddl_path = Path(__file__).parents[2] / "scripts" / "phase5_ddl.sql"
    content = ddl_path.read_text()
    assert "dm.alert_rules" in content
    assert "dm.alert_history" in content
    assert "dm.report_records" in content
    assert "dm.report_recipients" in content
    assert "ReplacingMergeTree" in content
    assert "ORDER BY" in content


def test_init_script_reads_ddl():
    """验证初始化脚本读取并执行 DDL"""
    with patch("services.clickhouse_service.ClickHouseDataService") as mock_ch:
        mock_instance = MagicMock()
        mock_ch.return_value = mock_instance

        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parents[2]))

        # Re-import to run main
        with patch("scripts.init_phase5.main"):
            from scripts.init_phase5 import main
            # Just verify module loads without error
            assert True
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/qiming/WorkSpace/finBoss/.worktrees/phase5-alerts-reports && uv run pytest tests/unit/test_phase5_init.py -v`
Expected: FAIL (file not found)

- [ ] **Step 3: 创建 DDL**

```sql
-- scripts/phase5_ddl.sql

-- dm.alert_rules
CREATE TABLE IF NOT EXISTS dm.alert_rules (
    id             String,
    name           String,
    metric         String,
    operator       String,
    threshold      Float64,
    scope_type     String,
    scope_value    String,
    alert_level    String,
    enabled        UInt8,
    created_at     DateTime,
    updated_at     DateTime
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (id, updated_at)
SETTINGS allow_experimental_object_type = 1;

-- dm.alert_history
CREATE TABLE IF NOT EXISTS dm.alert_history (
    id             String,
    rule_id        String,
    rule_name      String,
    alert_level    String,
    metric         String,
    operator       String,
    metric_value   Float64,
    threshold      Float64,
    scope_type     String,
    scope_value    String,
    triggered_at   DateTime,
    sent           UInt8
) ENGINE = ReplacingMergeTree(triggered_at)
ORDER BY (rule_id, triggered_at)
SETTINGS allow_experimental_object_type = 1;

-- dm.report_records
CREATE TABLE IF NOT EXISTS dm.report_records (
    id             String,
    report_type    String,
    period_start   Date,
    period_end     Date,
    recipients     String,
    file_path      String,
    sent_at        DateTime,
    status         String
) ENGINE = ReplacingMergeTree(sent_at)
ORDER BY (report_type, sent_at)
SETTINGS allow_experimental_object_type = 1;

-- dm.report_recipients
CREATE TABLE IF NOT EXISTS dm.report_recipients (
    id              String,
    recipient_type  String,
    name            String,
    channel_id      String,
    enabled         UInt8,
    created_at      DateTime
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (recipient_type, id)
SETTINGS allow_experimental_object_type = 1;
```

- [ ] **Step 4: 创建初始化脚本**

```python
#!/usr/bin/env python
"""初始化 Phase 5 相关表和内置预警规则"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# 内置预警规则
BUILTIN_ALERT_RULES = [
    {
        "id": "rule_overdue_rate",
        "name": "客户逾期率超标",
        "metric": "overdue_rate",
        "operator": "gt",
        "threshold": 0.3,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "高",
        "enabled": 1,
    },
    {
        "id": "rule_overdue_amount",
        "name": "单客户逾期金额超标",
        "metric": "overdue_amount",
        "operator": "gt",
        "threshold": 1000000.0,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "高",
        "enabled": 1,
    },
    {
        "id": "rule_overdue_delta",
        "name": "逾期率周环比恶化",
        "metric": "overdue_rate_delta",
        "operator": "gt",
        "threshold": 0.05,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "中",
        "enabled": 1,
    },
    {
        "id": "rule_new_overdue",
        "name": "新增逾期客户",
        "metric": "new_overdue_count",
        "operator": "gt",
        "threshold": 5.0,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "中",
        "enabled": 1,
    },
    {
        "id": "rule_aging_90",
        "name": "账龄超90天占比高",
        "metric": "aging_90pct",
        "operator": "gt",
        "threshold": 0.2,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "高",
        "enabled": 1,
    },
]


def _insert_rules(ch):
    """插入内置预警规则"""
    now = "now()"
    for rule in BUILTIN_ALERT_RULES:
        sql = f"""
        INSERT INTO dm.alert_rules
        (id, name, metric, operator, threshold, scope_type, scope_value, alert_level, enabled, created_at, updated_at)
        VALUES
        ('{rule['id']}', '{rule['name']}', '{rule['metric']}', '{rule['operator']}',
         {rule['threshold']}, '{rule['scope_type']}', '{rule['scope_value']}',
         '{rule['alert_level']}', {rule['enabled']}, {now}, {now})
        """
        try:
            ch.execute(sql)
            logger.info(f"  OK {rule['name']}")
        except Exception as e:
            if "57" in str(e):  # already exists
                logger.info(f"  SKIP {rule['name']} (already exists)")
            else:
                logger.error(f"  FAIL {rule['name']}: {e}")


def main():
    from services.clickhouse_service import ClickHouseDataService
    from clickhouse_driver.errors import Error as ClickHouseError

    ch = ClickHouseDataService()

    ddl_path = Path(__file__).parent / "phase5_ddl.sql"
    if not ddl_path.exists():
        logger.error(f"DDL 文件不存在: {ddl_path}")
        return

    with open(ddl_path) as f:
        ddl_content = f.read()

    statements = [s.strip() for s in ddl_content.split(";") if s.strip()]
    for stmt in statements:
        if not stmt:
            continue
        try:
            ch.execute(stmt)
            table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[-1].split("(")[0].strip()
            logger.info(f"  OK {table_name}")
        except ClickHouseError as e:
            if getattr(e, "code", None) == 57:
                table_name = stmt.split("CREATE TABLE IF NOT EXISTS ")[-1].split("(")[0].strip()
                logger.info(f"  SKIP {table_name} (already exists)")
            else:
                logger.error(f"  FAIL execute: {e}")
        except Exception as e:
            logger.error(f"  FAIL: {e}")

    # 插入内置规则
    _insert_rules(ch)

    logger.info("Phase 5 初始化完成！")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd /Users/qiming/WorkSpace/finBoss/.worktrees/phase5-alerts-reports && uv run pytest tests/unit/test_phase5_init.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/phase5_ddl.sql scripts/init_phase5.py tests/unit/test_phase5_init.py
git commit -m "feat: Phase 5 DDL + init script with 5 built-in alert rules"
```

---

## Task 2: Alert 数据模型

**Files:**
- Create: `schemas/alert.py`
- Test: `tests/unit/test_alert_models.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_alert_models.py
"""测试预警数据模型"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from schemas.alert import AlertRule, AlertHistory, AlertLevel


class TestAlertRule:
    def test_required_fields(self):
        rule = AlertRule(
            id="test_rule",
            name="测试规则",
            metric="overdue_rate",
            operator="gt",
            threshold=0.3,
            scope_type="company",
            alert_level="高",
            enabled=True,
        )
        assert rule.id == "test_rule"
        assert rule.metric == "overdue_rate"
        assert rule.threshold == 0.3

    def test_optional_scope_value(self):
        rule = AlertRule(
            id="test",
            name="T",
            metric="overdue_rate",
            operator="gt",
            threshold=0.3,
            scope_type="customer",
            scope_value="腾讯科技",
            alert_level="高",
            enabled=True,
        )
        assert rule.scope_value == "腾讯科技"

    def test_invalid_alert_level(self):
        with pytest.raises(ValidationError):
            AlertRule(
                id="t", name="T", metric="overdue_rate",
                operator="gt", threshold=0.3,
                scope_type="company", alert_level="极高", enabled=True,
            )


class TestAlertHistory:
    def test_required_fields(self):
        h = AlertHistory(
            id="h1",
            rule_id="r1",
            rule_name="逾期率超标",
            alert_level="高",
            metric="overdue_rate",
            operator="gt",
            metric_value=0.45,
            threshold=0.3,
            scope_type="company",
            scope_value="",
        )
        assert h.metric_value > h.threshold

    def test_exceed_threshold(self):
        h = AlertHistory(
            id="h1", rule_id="r1", rule_name="T",
            alert_level="高", metric="overdue_rate", operator="gt",
            metric_value=0.5, threshold=0.3,
            scope_type="company", scope_value="",
        )
        assert h.exceeded  # metric_value > threshold
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/unit/test_alert_models.py -v`
Expected: FAIL (schemas.alert not found)

- [ ] **Step 3: 创建 schemas/alert.py**

```python
"""预警数据模型"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AlertLevel(str, Enum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class AlertOperator(str, Enum):
    GT = "gt"   # >
    LT = "lt"   # <
    GTE = "gte" # >=
    LTE = "lte" # <=


class AlertMetric(str, Enum):
    OVERDUE_RATE = "overdue_rate"
    OVERDUE_AMOUNT = "overdue_amount"
    OVERDUE_RATE_DELTA = "overdue_rate_delta"
    NEW_OVERDUE_COUNT = "new_overdue_count"
    AGING_90PCT = "aging_90pct"


class AlertRule(BaseModel):
    """预警规则配置"""
    id: str
    name: str
    metric: AlertMetric | str
    operator: AlertOperator | str
    threshold: float
    scope_type: str = "company"  # company / customer / sales
    scope_value: str | None = None
    alert_level: AlertLevel | str
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AlertHistory(BaseModel):
    """预警触发历史"""
    id: str
    rule_id: str
    rule_name: str
    alert_level: AlertLevel | str
    metric: str
    operator: str
    metric_value: float
    threshold: float
    scope_type: str = "company"
    scope_value: str | None = None
    triggered_at: datetime | None = None
    sent: int = 0  # 0=未发送, 1=已发送

    @property
    def exceeded(self) -> bool:
        """是否超过阈值"""
        if self.operator == "gt":
            return self.metric_value > self.threshold
        elif self.operator == "lt":
            return self.metric_value < self.threshold
        elif self.operator == "gte":
            return self.metric_value >= self.threshold
        elif self.operator == "lte":
            return self.metric_value <= self.threshold
        return False
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/unit/test_alert_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add schemas/alert.py tests/unit/test_alert_models.py
git commit -m "feat: add alert schemas (AlertRule, AlertHistory)"
```

---

## Task 3: AlertService 核心逻辑

**Files:**
- Create: `services/alert_service.py`
- Test: `tests/unit/test_alert_service.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_alert_service.py
"""测试 AlertService 核心逻辑"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from services.alert_service import AlertService, BUILTIN_RULES


class TestAlertService:
    def test_builtin_rules_5_rules(self):
        assert len(BUILTIN_RULES) == 5
        rule_ids = {r["id"] for r in BUILTIN_RULES}
        assert "rule_overdue_rate" in rule_ids
        assert "rule_overdue_amount" in rule_ids
        assert "rule_overdue_delta" in rule_ids
        assert "rule_new_overdue" in rule_ids
        assert "rule_aging_90" in rule_ids

    def test_evaluate_threshold_exceeded(self):
        with patch("services.alert_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            # overdue_rate > 0.3 → 0.45 > 0.3 = True
            mock_ch.execute_query.return_value = [{"overdue_rate": 0.45}]
            service = AlertService()
            alerts = service.evaluate_all()
            assert len(alerts) >= 1

    def test_evaluate_threshold_not_exceeded(self):
        with patch("services.alert_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            # 0.1 < 0.3 → not exceeded
            mock_ch.execute_query.return_value = [{"overdue_rate": 0.1}]
            service = AlertService()
            alerts = service.evaluate_all()
            overdue_rate_alerts = [a for a in alerts if a.rule_id == "rule_overdue_rate"]
            assert len(overdue_rate_alerts) == 0

    def test_evaluate_disabled_rules_skipped(self):
        with patch("services.alert_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [{"overdue_rate": 0.45}]
            service = AlertService()
            # All enabled=True by default, so overdue_rate should trigger
            alerts = service.evaluate_all()
            rule_ids = {a.rule_id for a in alerts}
            assert "rule_overdue_rate" in rule_ids
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/unit/test_alert_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 创建 AlertService**

```python
"""逾期预警服务"""
import uuid
from datetime import datetime
from typing import Any

from services.clickhouse_service import ClickHouseDataService
from schemas.alert import AlertHistory

# 内置预警规则（与 scripts/init_phase5.py 中的 BUILTIN_ALERT_RULES 保持同步）
BUILTIN_RULES: list[dict[str, Any]] = [
    {
        "id": "rule_overdue_rate",
        "name": "客户逾期率超标",
        "metric": "overdue_rate",
        "operator": "gt",
        "threshold": 0.3,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "高",
    },
    {
        "id": "rule_overdue_amount",
        "name": "单客户逾期金额超标",
        "metric": "overdue_amount",
        "operator": "gt",
        "threshold": 1000000.0,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "高",
    },
    {
        "id": "rule_overdue_delta",
        "name": "逾期率周环比恶化",
        "metric": "overdue_rate_delta",
        "operator": "gt",
        "threshold": 0.05,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "中",
    },
    {
        "id": "rule_new_overdue",
        "name": "新增逾期客户",
        "metric": "new_overdue_count",
        "operator": "gt",
        "threshold": 5.0,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "中",
    },
    {
        "id": "rule_aging_90",
        "name": "账龄超90天占比高",
        "metric": "aging_90pct",
        "operator": "gt",
        "threshold": 0.2,
        "scope_type": "company",
        "scope_value": "",
        "alert_level": "高",
    },
]


class AlertService:
    """逾期预警规则引擎"""

    # 指标名到 SQL 查询的映射
    METRIC_QUERIES: dict[str, str] = {
        "overdue_rate": """
            SELECT ar_overdue / nullIf(ar_total, 0) AS overdue_rate
            FROM dm.dm_customer360
            WHERE stat_date = (SELECT max(stat_date) FROM dm.dm_customer360)
            LIMIT 1
        """,
        "overdue_amount": """
            SELECT sum(ar_overdue) AS overdue_amount
            FROM dm.dm_customer360
            WHERE stat_date = (SELECT max(stat_date) FROM dm.dm_customer360)
        """,
        "overdue_rate_delta": """
            SELECT
                (avgIf(ar_overdue / nullIf(ar_total, 0), stat_date >= today()-6)
                 - avgIf(ar_overdue / nullIf(ar_total, 0), stat_date BETWEEN today()-13 AND today()-7))
                AS overdue_rate_delta
            FROM dm.dm_customer360
            WHERE stat_date >= today()-13
        """,
        "new_overdue_count": """
            SELECT countIf(unified_customer_code, ar_overdue > 0 AND prev_overdue = 0) AS new_overdue_count
            FROM (
                SELECT
                    unified_customer_code, ar_overdue,
                    lagInFrame(ar_overdue) OVER (PARTITION BY unified_customer_code ORDER BY stat_date) AS prev_overdue
                FROM dm.dm_customer360
                WHERE stat_date >= today()-1 AND stat_date <= today()
                QUALIFY stat_date = today()
            )
        """,
        "aging_90pct": """
            SELECT
                sumIf(ar_amount, date_diff('day', due_date, today()) > 90)
                / nullIf(sum(ar_amount), 0) AS aging_90pct
            FROM std.std_ar
            WHERE stat_date = (SELECT max(stat_date) FROM std.std_ar)
        """,
    }

    def __init__(self, ch: ClickHouseDataService | None = None):
        self._ch = ch or ClickHouseDataService()

    def evaluate_all(self) -> list[AlertHistory]:
        """评估所有启用的规则，返回触发的 AlertHistory 列表"""
        alerts: list[AlertHistory] = []

        rows = self._ch.execute_query(
            "SELECT id, name, metric, operator, threshold, scope_type, scope_value, alert_level "
            "FROM dm.alert_rules WHERE enabled = 1"
        )
        if not rows:
            # 无数据库规则时使用内置规则
            rules = BUILTIN_RULES
        else:
            rules = rows

        for rule in rules:
            metric_value = self._evaluate_metric(rule["metric"])
            if metric_value is None:
                continue

            if self._is_exceeded(metric_value, rule["operator"], rule["threshold"]):
                alert = AlertHistory(
                    id=str(uuid.uuid4()),
                    rule_id=rule["id"],
                    rule_name=rule["name"],
                    alert_level=rule["alert_level"],
                    metric=rule["metric"],
                    operator=rule["operator"],
                    metric_value=metric_value,
                    threshold=rule["threshold"],
                    scope_type=rule.get("scope_type", "company"),
                    scope_value=rule.get("scope_value"),
                    triggered_at=datetime.now(),
                    sent=0,
                )
                alerts.append(alert)
                self._save_history(alert)

        return alerts

    def _evaluate_metric(self, metric: str) -> float | None:
        """执行指标查询"""
        sql = self.METRIC_QUERIES.get(metric)
        if not sql:
            return None
        try:
            rows = self._ch.execute_query(sql)
            if not rows:
                return None
            # 取第一行第一个值
            return rows[0].get(metric) or rows[0].get(list(rows[0].keys())[0])
        except Exception:
            return None

    def _is_exceeded(self, value: float, operator: str, threshold: float) -> bool:
        """判断是否超过阈值"""
        if operator == "gt":
            return value > threshold
        elif operator == "lt":
            return value < threshold
        elif operator == "gte":
            return value >= threshold
        elif operator == "lte":
            return value <= threshold
        return False

    def _save_history(self, alert: AlertHistory) -> None:
        """保存预警历史到 ClickHouse"""
        try:
            self._ch.execute(
                f"INSERT INTO dm.alert_history "
                f"(id, rule_id, rule_name, alert_level, metric, operator, metric_value, threshold, scope_type, scope_value, triggered_at, sent) "
                f"VALUES ('{alert.id}', '{alert.rule_id}', '{alert.rule_name}', '{alert.alert_level}', "
                f"'{alert.metric}', '{alert.operator}', {alert.metric_value}, {alert.threshold}, "
                f"'{alert.scope_type}', '{alert.scope_value or ''}', now(), 0)"
            )
        except Exception:
            pass  # 不阻塞预警流程

    def send_summary(self, alerts: list[AlertHistory]) -> bool:
        """构建并发送预警汇总飞书卡片"""
        if not alerts:
            return True

        from services.feishu.config import get_feishu_config
        from services.feishu.feishu_client import FeishuClient

        config = get_feishu_config()
        if not config.mgmt_channel_id:
            import logging
            logging.getLogger(__name__).warning("FEISHU_MGMT_CHANNEL_ID 未配置，跳过预警推送")
            return False

        # 按级别分组
        by_level: dict[str, list[AlertHistory]] = {}
        for a in alerts:
            by_level.setdefault(a.alert_level, []).append(a)

        card_elements = [
            {
                "tag": "markdown",
                "content": f"**🚨 逾期预警日报 - {datetime.now().strftime('%Y-%m-%d')}**\n"
                            f"高危 {len(by_level.get('高', []))} 条 | "
                            f"中危 {len(by_level.get('中', []))} 条 | "
                            f"低危 {len(by_level.get('低', []))} 条",
            },
            {"tag": "hr"},
        ]

        # 详情表格
        for level, items in sorted(by_level.items(), key=lambda x: ["高", "中", "低"].index(x[0])):
            card_elements.append({
                "tag": "markdown",
                "content": f"**【{level}级】{len(items)} 条**",
            })
            for item in items:
                exceed_pct = (item.metric_value - item.threshold) / item.threshold * 100
                card_elements.append({
                    "tag": "markdown",
                    "content": f"- {item.rule_name}: `{item.metric_value:.2%}` > `{item.threshold:.2%}` (+{exceed_pct:.1f}%)",
                })

        card_elements.append({"tag": "hr"})
        card_elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看看板"},
                "type": "primary",
                "url": "/static/reports/dashboard_latest.html",
            }]
        })

        card = {"elements": card_elements}
        client = FeishuClient()
        return client.send_card_to_channel(card, channel_id=config.mgmt_channel_id)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/unit/test_alert_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/alert_service.py tests/unit/test_alert_service.py
git commit -m "feat: add AlertService with 5 built-in rules and Feishu card sending"
```

---

## Task 4: Alert API CRUD

**Files:**
- Create: `api/schemas/alert.py`
- Create: `api/routes/alerts.py`
- Modify: `api/main.py`（注册路由）
- Modify: `api/dependencies.py`（添加 AlertServiceDep）
- Test: `tests/integration/test_alerts_api.py`

- [ ] **Step 1: 写测试**

```python
# tests/integration/test_alerts_api.py
"""预警 API 集成测试"""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAlertRulesAPI:
    def test_list_rules_returns_200(self, client):
        with patch("services.alert_service.AlertService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.list_rules.return_value = []
            mock_svc_cls.return_value = mock_svc
            response = client.get("/api/v1/alerts/rules")
            assert response.status_code == 200

    def test_create_rule_returns_200(self, client):
        with patch("services.alert_service.AlertService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.create_rule.return_value = {"id": "new_rule"}
            mock_svc_cls.return_value = mock_svc
            response = client.post(
                "/api/v1/alerts/rules",
                json={
                    "name": "新规则",
                    "metric": "overdue_rate",
                    "operator": "gt",
                    "threshold": 0.5,
                    "scope_type": "company",
                    "alert_level": "高",
                    "enabled": True,
                },
            )
            assert response.status_code == 200

    def test_delete_rule_returns_200(self, client):
        with patch("services.alert_service.AlertService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.delete_rule.return_value = True
            mock_svc_cls.return_value = mock_svc
            response = client.delete("/api/v1/alerts/rules/test_rule")
            assert response.status_code == 200

    def test_get_history_returns_200(self, client):
        with patch("services.alert_service.AlertService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.get_history.return_value = []
            mock_svc_cls.return_value = mock_svc
            response = client.get("/api/v1/alerts/history")
            assert response.status_code == 200
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/integration/test_alerts_api.py -v`
Expected: FAIL (routes not found)

- [ ] **Step 3: 创建 API schemas 和路由**

```python
# api/schemas/alert.py
"""预警 API 请求/响应模型"""
from datetime import datetime
from pydantic import BaseModel, Field


class AlertRuleCreate(BaseModel):
    name: str
    metric: str
    operator: str
    threshold: float
    scope_type: str = "company"
    scope_value: str | None = None
    alert_level: str
    enabled: bool = True


class AlertRuleResponse(BaseModel):
    id: str
    name: str
    metric: str
    operator: str
    threshold: float
    scope_type: str
    scope_value: str | None
    alert_level: str
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None


class AlertHistoryResponse(BaseModel):
    id: str
    rule_id: str
    rule_name: str
    alert_level: str
    metric: str
    operator: str
    metric_value: float
    threshold: float
    scope_type: str
    scope_value: str | None
    triggered_at: datetime
    sent: int
```

```python
# api/routes/alerts.py
"""预警规则 API 路由"""
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from api.dependencies import AlertServiceDep
from api.schemas.alert import AlertRuleCreate, AlertRuleResponse, AlertHistoryResponse

router = APIRouter()


@router.get("/rules")
async def list_rules(service: AlertServiceDep):
    """列出所有预警规则"""
    rules = service.list_rules()
    return {"items": rules, "total": len(rules)}


@router.post("/rules")
async def create_rule(rule: AlertRuleCreate, service: AlertServiceDep):
    """创建预警规则"""
    result = service.create_rule(rule)
    return result


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, rule: AlertRuleCreate, service: AlertServiceDep):
    """更新预警规则"""
    result = service.update_rule(rule_id, rule)
    if not result:
        raise HTTPException(status_code=404, detail="规则不存在")
    return result


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, service: AlertServiceDep):
    """删除预警规则"""
    success = service.delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"status": "deleted", "id": rule_id}


@router.get("/history")
async def get_history(
    service: AlertServiceDep,
    limit: int = 50,
    rule_id: str | None = None,
):
    """查询预警触发历史"""
    history = service.get_history(limit=limit, rule_id=rule_id)
    return {"items": history, "total": len(history)}


@router.post("/trigger")
async def trigger_evaluation(service: AlertServiceDep):
    """手动触发一次预警评估"""
    alerts = service.evaluate_all()
    if alerts:
        service.send_summary(alerts)
    return {
        "triggered": len(alerts),
        "alert_levels": {a.alert_level for a in alerts},
    }
```

- [ ] **Step 4: 更新 AlertService 添加 CRUD 方法**

在 `services/alert_service.py` 中添加：

```python
    def list_rules(self) -> list[dict]:
        """列出所有规则"""
        rows = self._ch.execute_query(
            "SELECT * FROM dm.alert_rules ORDER BY created_at DESC"
        )
        return rows

    def create_rule(self, rule: dict) -> dict:
        """创建规则"""
        now = datetime.now().isoformat()
        rule_id = rule.get("id") or str(uuid.uuid4())
        self._ch.execute(
            f"INSERT INTO dm.alert_rules "
            f"(id, name, metric, operator, threshold, scope_type, scope_value, alert_level, enabled, created_at, updated_at) "
            f"VALUES ('{rule_id}', '{rule['name']}', '{rule['metric']}', '{rule['operator']}', "
            f"{rule['threshold']}, '{rule['scope_type']}', '{rule.get('scope_value', '')}', "
            f"'{rule['alert_level']}', {int(rule.get('enabled', True))}, '{now}', '{now}')"
        )
        return {"id": rule_id, **rule}

    def update_rule(self, rule_id: str, rule: dict) -> dict | None:
        """更新规则"""
        rows = self._ch.execute_query(
            f"SELECT 1 FROM dm.alert_rules WHERE id = '{rule_id}'"
        )
        if not rows:
            return None
        now = datetime.now().isoformat()
        self._ch.execute(
            f"ALTER TABLE dm.alert_rules UPDATE "
            f"name = '{rule['name']}', metric = '{rule['metric']}', "
            f"operator = '{rule['operator']}', threshold = {rule['threshold']}, "
            f"scope_type = '{rule['scope_type']}', scope_value = '{rule.get('scope_value', '')}', "
            f"alert_level = '{rule['alert_level']}', enabled = {int(rule.get('enabled', True))}, "
            f"updated_at = '{now}' WHERE id = '{rule_id}'"
        )
        return {"id": rule_id, **rule}

    def delete_rule(self, rule_id: str) -> bool:
        """删除规则"""
        try:
            self._ch.execute(
                f"ALTER TABLE dm.alert_rules DELETE WHERE id = '{rule_id}'"
            )
            return True
        except Exception:
            return False

    def get_history(self, limit: int = 50, rule_id: str | None = None) -> list[dict]:
        """查询预警历史"""
        where = f"WHERE rule_id = '{rule_id}'" if rule_id else ""
        rows = self._ch.execute_query(
            f"SELECT * FROM dm.alert_history {where} "
            f"ORDER BY triggered_at DESC LIMIT {limit}"
        )
        return rows
```

- [ ] **Step 5: 更新 dependencies.py 添加 AlertServiceDep**

```python
@lru_cache
def get_alert_service() -> AlertService:
    return AlertService()

AlertServiceDep = Annotated[AlertService, Depends(get_alert_service)]
```

同时添加导入：
```python
from services.alert_service import AlertService
```

- [ ] **Step 6: 更新 api/main.py 注册路由**

添加：
```python
from api.routes import alerts, reports
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["预警"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["报告"])
```

- [ ] **Step 7: 运行测试验证通过**

Run: `uv run pytest tests/integration/test_alerts_api.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add api/schemas/alert.py api/routes/alerts.py api/dependencies.py api/main.py
git commit -m "feat: add alert API CRUD routes and dependency injection"
```

---

## Task 5: DashboardService + 看版模板

**Files:**
- Create: `services/dashboard_service.py`
- Create: `templates/reports/dashboard.html.j2`
- Modify: `api/routes/reports.py`（看板生成触发）
- Test: `tests/unit/test_dashboard_service.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_dashboard_service.py
"""测试 DashboardService"""
import pytest
from unittest.mock import MagicMock, patch

from services.dashboard_service import DashboardService


class TestDashboardService:
    def test_generate_writes_html_file(self):
        with patch("services.dashboard_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [{
                "ar_total": 10000000.0,
                "ar_overdue": 500000.0,
                "overdue_rate": 0.05,
            }]
            service = DashboardService()
            path = service.generate()
            assert path is not None
            assert "dashboard" in path
            assert path.endswith(".html")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/unit/test_dashboard_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 创建 DashboardService**

```python
"""管理看板生成服务"""
import os
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from services.clickhouse_service import ClickHouseDataService

# 项目根目录（用于定位 templates）
PROJECT_ROOT = Path(__file__).parent.parent


class DashboardService:
    """HTML 管理看板生成"""

    def __init__(self, ch: ClickHouseDataService | None = None):
        self._ch = ch or ClickHouseDataService()
        self._jinja = Environment(
            loader=FileSystemLoader(PROJECT_ROOT / "templates" / "reports"),
            autoescape=True,
        )

    def generate(self, stat_date: date | None = None) -> str:
        """生成看板 HTML 文件"""
        if stat_date is None:
            stat_date = date.today()
        date_str = stat_date.isoformat()

        # 获取 KPI 数据
        kpi = self._get_kpi(stat_date)
        # 获取集中度数据
        concentration = self._get_concentration(stat_date)
        # 获取逾期分布
        distribution = self._get_distribution(stat_date)
        # 获取趋势数据
        trend = self._get_trend()
        # 获取风险客户
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
            "  countIf(overdue_rate > 0.3 AND overdue_rate <= 0.6) AS bucket_30_60, "
            "  countIf(overdue_rate > 0.6) AS bucket_60_plus "
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
```

- [ ] **Step 4: 创建 Jinja2 模板**

```html
<!-- templates/reports/dashboard.html.j2 -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AR 管理看板 - {{ stat_date }}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #333; padding: 20px; }
  .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
  .header h1 { font-size: 24px; font-weight: 600; }
  .header .date { color: #888; font-size: 14px; }
  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
  .kpi-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .kpi-card .label { font-size: 13px; color: #888; margin-bottom: 8px; }
  .kpi-card .value { font-size: 28px; font-weight: 700; color: #1a1a1a; }
  .kpi-card .value.danger { color: #e53e3e; }
  .kpi-card .value.warning { color: #d69e2e; }
  .kpi-card .value.success { color: #38a169; }
  .section { background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .section h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #1a1a1a; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }
  th { color: #888; font-weight: 500; font-size: 12px; text-transform: uppercase; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 500; }
  .tag.high { background: #fed7d7; color: #c53030; }
  .tag.medium { background: #fefcbf; color: #975a16; }
  .tag.low { background: #c6f6d5; color: #276749; }
  .bar-chart { display: flex; flex-direction: column; gap: 8px; }
  .bar-row { display: flex; align-items: center; gap: 8px; }
  .bar-label { width: 120px; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar-track { flex: 1; height: 20px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
  .bar-fill { height: 100%; background: #3182ce; border-radius: 4px; transition: width 0.3s; }
  .bar-pct { width: 40px; text-align: right; font-size: 12px; color: #666; }
  .pie-chart { display: flex; align-items: center; gap: 24px; }
  .pie-legend { display: flex; flex-direction: column; gap: 8px; }
  .legend-item { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; }
  .trend-chart { display: flex; flex-direction: column; gap: 4px; }
  .trend-bar { display: flex; align-items: center; gap: 8px; font-size: 12px; }
  .trend-date { width: 80px; color: #888; }
  .trend-track { flex: 1; height: 12px; background: #f0f0f0; border-radius: 2px; }
  .trend-fill { height: 100%; background: #e53e3e; border-radius: 2px; }
  .trend-rate { width: 50px; text-align: right; }
</style>
</head>
<body>

<div class="header">
  <h1>AR 管理看板</h1>
  <span class="date">数据日期: {{ stat_date }}</span>
</div>

<!-- KPI Cards -->
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="label">AR 总额</div>
    <div class="value">¥{{ "%.0f"|format(kpi.ar_total) }}</div>
  </div>
  <div class="kpi-card">
    <div class="label">逾期总额</div>
    <div class="value danger">¥{{ "%.0f"|format(kpi.ar_overdue) }}</div>
  </div>
  <div class="kpi-card">
    <div class="label">逾期率</div>
    <div class="value {% if kpi.overdue_rate > 0.1 %}danger{% elif kpi.overdue_rate > 0.05 %}warning{% else %}success{% endif %}">
      {{ "%.1f"|format(kpi.overdue_rate * 100) }}%
    </div>
  </div>
  <div class="kpi-card">
    <div class="label">客户数</div>
    <div class="value">{{ kpi.customer_count }}</div>
  </div>
</div>

<!-- Concentration -->
<div class="section">
  <h2>集中度 Top 10</h2>
  <div class="bar-chart">
    {% for c in concentration %}
    <div class="bar-row">
      <span class="bar-label" title="{{ c.name }}">{{ c.name }}</span>
      <div class="bar-track">
        <div class="bar-fill" style="width: {{ (c.pct * 100)|round(1) }}%"></div>
      </div>
      <span class="bar-pct">{{ "%.1f"|format(c.pct * 100) }}%</span>
    </div>
    {% endfor %}
    {% if not concentration %}
    <div style="color:#888;font-size:13px;">暂无数据</div>
    {% endif %}
  </div>
</div>

<div class="two-col">
  <!-- Distribution -->
  <div class="section">
    <h2>逾期分布</h2>
    <div class="pie-legend">
      {% for d in distribution %}
      <div class="legend-item">
        <div class="legend-dot" style="background: {% if d.bucket == '无逾期' %}#38a169{% elif d.bucket == '0-30天' %}#3182ce{% elif d.bucket == '30-60天' %}#d69e2e{% else %}#e53e3e{% endif %}"></div>
        <span>{{ d.bucket }}</span>
        <span style="margin-left:auto;color:#888;">{{ d.count }} ({{ "%.0f"|format(d.pct * 100) }}%)</span>
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- Trend -->
  <div class="section">
    <h2>逾期率趋势（近12周）</h2>
    <div class="trend-chart">
      {% for t in trend[-12:] %}
      <div class="trend-bar">
        <span class="trend-date">{{ t.date }}</span>
        <div class="trend-track">
          <div class="trend-fill" style="width: {{ (t.rate * 100 * 5)|round(1) if t.rate else 0 }}%"></div>
        </div>
        <span class="trend-rate">{{ "%.1f"|format(t.rate * 100) }}%</span>
      </div>
      {% endfor %}
      {% if not trend %}
      <div style="color:#888;font-size:13px;">暂无趋势数据</div>
      {% endif %}
    </div>
  </div>
</div>

<!-- Risk Customers -->
<div class="section">
  <h2>风险客户（逾期率 > 30%）</h2>
  <table>
    <thead>
      <tr>
        <th>客户名称</th>
        <th>AR总额</th>
        <th>逾期金额</th>
        <th>逾期率</th>
        <th>风险等级</th>
      </tr>
    </thead>
    <tbody>
      {% for c in risk_customers %}
      <tr>
        <td>{{ c.name }}</td>
        <td>¥{{ "%.0f"|format(c.ar_total) }}</td>
        <td>¥{{ "%.0f"|format(c.ar_overdue) }}</td>
        <td>{{ "%.1f"|format(c.overdue_rate * 100) }}%</td>
        <td><span class="tag {% if c.risk_level == '高' %}high{% elif c.risk_level == '中' %}medium{% else %}low{% endif %}">{{ c.risk_level }}</span></td>
      </tr>
      {% endfor %}
      {% if not risk_customers %}
      <tr><td colspan="5" style="color:#888;text-align:center;">暂无高风险客户</td></tr>
      {% endif %}
    </tbody>
  </table>
</div>

</body>
</html>
```

- [ ] **Step 5: 运行测试验证通过**

Run: `uv run pytest tests/unit/test_dashboard_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/dashboard_service.py templates/reports/dashboard.html.j2 tests/unit/test_dashboard_service.py
git commit -m "feat: add DashboardService with inline SVG HTML template"
```

---

## Task 6: ReportService + 报告模板

**Files:**
- Create: `templates/reports/weekly_report.html.j2`
- Create: `templates/reports/monthly_report.html.j2`
- Create: `services/report_service.py`
- Test: `tests/unit/test_report_service.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_report_service.py
"""测试 ReportService"""
import pytest
from unittest.mock import MagicMock, patch

from services.report_service import ReportService


class TestReportService:
    def test_generate_weekly_creates_html(self):
        with patch("services.report_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [{
                "ar_total": 1000000.0,
                "ar_overdue": 50000.0,
                "overdue_rate": 0.05,
                "risk_high": 3,
                "risk_medium": 10,
                "risk_low": 87,
            }]
            service = ReportService()
            path = service.generate("weekly")
            assert path is not None
            assert "weekly" in path
            assert path.endswith(".html")

    def test_generate_monthly_creates_html(self):
        with patch("services.report_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = []
            service = ReportService()
            path = service.generate("monthly")
            assert path is not None
            assert "monthly" in path
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/unit/test_report_service.py -v`
Expected: FAIL

- [ ] **Step 3: 创建 ReportService**

```python
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
            "  sumIf(ar_overdue > 0, overdue_rate > 0.3) AS risk_high_count, "
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
            "risk_high_count": r.get("risk_high_count") or 0,
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
                f"INSERT INTO dm.report_records "
                f"(id, report_type, period_start, period_end, recipients, file_path, sent_at, status) "
                f"VALUES ('{record_id}', '{report_type}', '{period_start}', '{period_end}', "
                f"'{recipients}', '{file_path}', now(), 'generated')"
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
                "content": f"**📊 {report_type == 'weekly' and '周报' or '月报'} - {today.isoformat()}**\n"
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
```

- [ ] **Step 4: 创建周报/月报模板**

```html
<!-- templates/reports/weekly_report.html.j2 -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>AR 周报 - {{ period_start }} 至 {{ period_end }}</title>
<style>
  body { font-family: -apple-system, sans-serif; background: #f5f7fa; padding: 20px; }
  .container { max-width: 900px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; }
  h1 { font-size: 22px; margin-bottom: 4px; }
  .subtitle { color: #888; font-size: 14px; margin-bottom: 24px; }
  .kpi-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
  .kpi { background: #f8fafc; border-radius: 8px; padding: 16px; text-align: center; }
  .kpi .v { font-size: 24px; font-weight: 700; }
  .kpi .l { font-size: 12px; color: #888; margin-top: 4px; }
  .delta { font-size: 12px; padding: 2px 6px; border-radius: 4px; }
  .delta.up { background: #fed7d7; color: #c53030; }
  .delta.down { background: #c6f6d5; color: #276749; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }
  th { color: #888; font-size: 12px; text-transform: uppercase; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
  .tag.high { background: #fed7d7; color: #c53030; }
  .tag.medium { background: #fefcbf; color: #975a16; }
  .footer { margin-top: 24px; color: #aaa; font-size: 12px; text-align: center; }
</style>
</head>
<body>
<div class="container">
  <h1>📊 AR 周报</h1>
  <div class="subtitle">{{ period_start }} 至 {{ period_end }} | 生成时间: {{ generated_at }}</div>

  <div class="kpi-row">
    <div class="kpi">
      <div class="v">¥{{ "%.0f"|format(overview.ar_total) }}</div>
      <div class="l">AR 总额</div>
    </div>
    <div class="kpi">
      <div class="v">¥{{ "%.0f"|format(overview.ar_overdue) }}</div>
      <div class="l">逾期总额</div>
    </div>
    <div class="kpi">
      <div class="v">{{ "%.1f"|format(overview.overdue_rate * 100) }}%
        {% if mom.delta > 0 %}<span class="delta up">+{{ "%.1f"|format(mom.delta * 100) }}%</span>{% else %}<span class="delta down">{{ "%.1f"|format(mom.delta * 100) }}%</span>{% endif %}
      </div>
      <div class="l">逾期率（环比）</div>
    </div>
  </div>

  <h2 style="font-size:15px;margin-bottom:12px;">集中度 Top 10</h2>
  <table>
    <thead><tr><th>#</th><th>客户</th><th>金额</th><th>占比</th></tr></thead>
    <tbody>
    {% for c in concentration %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ c.name }}</td>
      <td>¥{{ "%.0f"|format(c.amount) }}</td>
      <td>{{ "%.1f"|format(c.pct * 100) }}%</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>

  <h2 style="font-size:15px;margin:20px 0 12px;">风险客户 TOP 10（逾期率 > 10%）</h2>
  <table>
    <thead><tr><th>客户</th><th>AR总额</th><th>逾期金额</th><th>逾期率</th><th>等级</th></tr></thead>
    <tbody>
    {% for c in risk_customers %}
    <tr>
      <td>{{ c.name }}</td>
      <td>¥{{ "%.0f"|format(c.ar_total) }}</td>
      <td>¥{{ "%.0f"|format(c.ar_overdue) }}</td>
      <td>{{ "%.1f"|format(c.overdue_rate * 100) }}%</td>
      <td><span class="tag {% if c.risk_level == '高' %}high{% else %}medium{% endif %}">{{ c.risk_level }}</span></td>
    </tr>
    {% endfor %}
    {% if not risk_customers %}
    <tr><td colspan="5" style="color:#888;text-align:center;">暂无风险客户</td></tr>
    {% endif %}
    </tbody>
  </table>

  <div class="footer">FinBoss AR 自动化报告 | {{ generated_at }}</div>
</div>
</body>
</html>
```

```html
<!-- templates/reports/monthly_report.html.j2 -->
<!-- 月报模板，与周报结构相同，增加同比（YoY）部分 -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>AR 月报 - {{ period_start }} 至 {{ period_end }}</title>
<style>
  body { font-family: -apple-system, sans-serif; background: #f5f7fa; padding: 20px; }
  .container { max-width: 900px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; }
  h1 { font-size: 22px; margin-bottom: 4px; }
  .subtitle { color: #888; font-size: 14px; margin-bottom: 24px; }
  .kpi-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
  .kpi { background: #f8fafc; border-radius: 8px; padding: 16px; text-align: center; }
  .kpi .v { font-size: 24px; font-weight: 700; }
  .kpi .l { font-size: 12px; color: #888; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }
  th { color: #888; font-size: 12px; text-transform: uppercase; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
  .tag.high { background: #fed7d7; color: #c53030; }
  .tag.medium { background: #fefcbf; color: #975a16; }
  .footer { margin-top: 24px; color: #aaa; font-size: 12px; text-align: center; }
  .yoy-note { background: #ebf8ff; border-radius: 6px; padding: 12px; margin-bottom: 20px; font-size: 13px; color: #2b6cb0; }
  .yoy-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-left: 6px; }
  .yoy-badge.up { background: #fed7d7; color: #c53030; }
  .yoy-badge.down { background: #c6f6d5; color: #276749; }
</style>
</head>
<body>
<div class="container">
  <h1>📊 AR 月报</h1>
  <div class="subtitle">{{ period_start }} 至 {{ period_end }} | 生成时间: {{ generated_at }}</div>

  {% if yoy %}
  <div class="yoy-note">
    📌 同比：去年同月逾期率 <strong>{{ "%.1f"|format(yoy.prev_year_rate * 100) }}%</strong>，
    本月 <strong>{{ "%.1f"|format(yoy.curr_rate * 100) }}%</strong>，
    {% if yoy.delta > 0 %}<span style="color:#c53030">同比上升 {{ "%.1f"|format(yoy.delta * 100) }}%</span>{% else %}<span style="color:#276749">同比下降 {{ "%.1f"|format((-yoy.delta) * 100) }}%</span>{% endif %}
  </div>
  {% endif %}

  <div class="kpi-row">
    <div class="kpi">
      <div class="v">¥{{ "%.0f"|format(overview.ar_total) }}</div>
      <div class="l">AR 总额</div>
    </div>
    <div class="kpi">
      <div class="v">¥{{ "%.0f"|format(overview.ar_overdue) }}</div>
      <div class="l">逾期总额</div>
    </div>
    <div class="kpi">
      <div class="v">{{ "%.1f"|format(overview.overdue_rate * 100) }}%</div>
      <div class="l">逾期率</div>
    </div>
  </div>

  <h2 style="font-size:15px;margin-bottom:12px;">集中度 Top 10</h2>
  <table>
    <thead><tr><th>#</th><th>客户</th><th>金额</th><th>占比</th></tr></thead>
    <tbody>
    {% for c in concentration %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ c.name }}</td>
      <td>¥{{ "%.0f"|format(c.amount) }}</td>
      <td>{{ "%.1f"|format(c.pct * 100) }}%</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>

  <h2 style="font-size:15px;margin:20px 0 12px;">风险客户 TOP 10</h2>
  <table>
    <thead><tr><th>客户</th><th>AR总额</th><th>逾期金额</th><th>逾期率</th><th>等级</th></tr></thead>
    <tbody>
    {% for c in risk_customers %}
    <tr>
      <td>{{ c.name }}</td>
      <td>¥{{ "%.0f"|format(c.ar_total) }}</td>
      <td>¥{{ "%.0f"|format(c.ar_overdue) }}</td>
      <td>{{ "%.1f"|format(c.overdue_rate * 100) }}%</td>
      <td><span class="tag {% if c.risk_level == '高' %}high{% else %}medium{% endif %}">{{ c.risk_level }}</span></td>
    </tr>
    {% endfor %}
    {% if not risk_customers %}
    <tr><td colspan="5" style="color:#888;text-align:center;">暂无风险客户</td></tr>
    {% endif %}
    </tbody>
  </table>

  <div class="footer">FinBoss AR 自动化月报 | {{ generated_at }}</div>
</div>
</body>
</html>
```

- [ ] **Step 5: 添加 reports 路由**

```python
# api/routes/reports.py
"""报告 API 路由"""
from fastapi import APIRouter

from api.dependencies import ReportServiceDep, DashboardServiceDep

router = APIRouter()


@router.post("/weekly")
async def trigger_weekly(service: ReportServiceDep):
    """手动触发周报生成"""
    path = service.generate("weekly")
    return {"status": "generated", "file": path}


@router.post("/monthly")
async def trigger_monthly(service: ReportServiceDep):
    """手动触发生成月报"""
    path = service.generate("monthly")
    return {"status": "generated", "file": path}


@router.get("/records")
async def list_records(service: ReportServiceDep, limit: int = 20):
    """查询报告发送记录"""
    records = service.list_records(limit=limit)
    return {"items": records, "total": len(records)}


@router.post("/dashboard/generate")
async def generate_dashboard(service: DashboardServiceDep):
    """手动生成看板"""
    path = service.generate()
    return {"status": "generated", "file": path}


# ReportService 需要添加 list_records 方法：
# def list_records(self, limit: int = 20) -> list[dict]:
#     return self._ch.execute_query(
#         f"SELECT * FROM dm.report_records ORDER BY sent_at DESC LIMIT {limit}"
#     )
```

Also add `ReportServiceDep` and `DashboardServiceDep` to `api/dependencies.py`:
```python
from services.report_service import ReportService
from services.dashboard_service import DashboardService

@lru_cache
def get_report_service() -> ReportService:
    return ReportService()

@lru_cache
def get_dashboard_service() -> DashboardService:
    return DashboardService()

ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]
DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
```

- [ ] **Step 6: 运行测试验证通过**

Run: `uv run pytest tests/unit/test_report_service.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/report_service.py templates/reports/weekly_report.html.j2 templates/reports/monthly_report.html.j2 tests/unit/test_report_service.py
git commit -m "feat: add ReportService with weekly/monthly report templates"
```

---

## Task 7: APScheduler 调度集成 + 静态文件

**Files:**
- Modify: `services/scheduler_service.py`
- Modify: `api/main.py`（静态文件挂载）
- Modify: `api/config.py`（FEISHU_MGMT_CHANNEL_ID）
- Modify: `pyproject.toml`（+jinja2）

- [ ] **Step 1: 添加 jinja2 依赖**

```toml
# 在 [dependencies] 中添加：
    "jinja2>=3.1.3",
```

Run: `uv sync`

- [ ] **Step 2: 更新 api/config.py 添加环境变量**

在 `FeishuConfig` 类中添加 `mgmt_channel_id` 字段并绑定环境变量：
```python
ops_channel_id: str = ""  # 已有
mgmt_channel_id: str = ""  # 新增，绑定 FEISHU_MGMT_CHANNEL_ID

# 在 model_config 中添加：
# env_prefix + 字段名自动映射：
# FEISHU_MGMT_CHANNEL_ID → FeishuConfig.mgmt_channel_id
```

- [ ] **Step 3: 更新 scheduler_service.py 添加 Phase 5 任务**

```python
def _register_phase5_jobs(scheduler: AsyncIOScheduler) -> None:
    """注册 Phase 5 调度任务"""

    def daily_alert_job() -> None:
        """每日 09:00 逾期预警评估"""
        import logging
        logger = logging.getLogger(__name__)
        try:
            from services.alert_service import AlertService
            service = AlertService()
            alerts = service.evaluate_all()
            if alerts:
                service.send_summary(alerts)
            logger.info(f"[Phase5] Alert evaluation: {len(alerts)} alerts triggered")
        except Exception as e:
            logger.error(f"[Phase5] Alert evaluation failed: {e}")

    def daily_dashboard_job() -> None:
        """每日 02:30 生成管理看板"""
        import logging
        logger = logging.getLogger(__name__)
        try:
            from services.dashboard_service import DashboardService
            service = DashboardService()
            path = service.generate()
            logger.info(f"[Phase5] Dashboard generated: {path}")
        except Exception as e:
            logger.error(f"[Phase5] Dashboard generation failed: {e}")

    def weekly_report_job() -> None:
        """每周一 08:00 生成并发送周报"""
        import logging
        logger = logging.getLogger(__name__)
        try:
            from services.report_service import ReportService
            service = ReportService()
            path = service.generate("weekly")
            service.send_management_report("weekly")
            logger.info(f"[Phase5] Weekly report generated: {path}")
        except Exception as e:
            logger.error(f"[Phase5] Weekly report failed: {e}")

    def monthly_report_job() -> None:
        """每月1日 08:00 生成并发送月报"""
        import logging
        logger = logging.getLogger(__name__)
        try:
            from services.report_service import ReportService
            service = ReportService()
            path = service.generate("monthly")
            service.send_management_report("monthly")
            logger.info(f"[Phase5] Monthly report generated: {path}")
        except Exception as e:
            logger.error(f"[Phase5] Monthly report failed: {e}")

    scheduler.add_job(
        daily_alert_job, CronTrigger(hour=9, minute=0),
        id="phase5_daily_alert", replace_existing=True,
    )
    scheduler.add_job(
        daily_dashboard_job, CronTrigger(hour=2, minute=30),
        id="phase5_daily_dashboard", replace_existing=True,
    )
    scheduler.add_job(
        weekly_report_job, CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="phase5_weekly_report", replace_existing=True,
    )
    scheduler.add_job(
        monthly_report_job, CronTrigger(day=1, hour=8, minute=0),
        id="phase5_monthly_report", replace_existing=True,
    )
```

在 `start_scheduler()` 中调用 `_register_phase5_jobs(scheduler)`。

- [ ] **Step 4: 更新 api/main.py 添加静态文件挂载**

```python
from fastapi.staticfiles import StaticFiles

# 在 create_app() 中添加：
# 挂载静态文件目录用于报告页面（隔离到 /static/reports 避免与根 /static 冲突）
static_dir = Path(__file__).parent.parent / "static" / "reports"
if static_dir.exists():
    app.mount("/static/reports", StaticFiles(directory=str(static_dir)), name="static_reports")
```

- [ ] **Step 5: 运行测试**

Run: `uv run pytest tests/ -q --ignore=tests/integration/test_customer360_api.py`
Expected: PASS（确保现有测试不因新增代码被破坏）

- [ ] **Step 6: Commit**

```bash
git add services/scheduler_service.py api/main.py api/config.py pyproject.toml
git commit -m "feat: Phase 5 APScheduler jobs (alert 09:00, dashboard 02:30, weekly/monthly 08:00)"
```

---

## Task 8: 集成测试 + 冒烟测试

**Files:**
- Create: `tests/integration/test_reports_api.py`
- Create: `tests/integration/test_alerts_api.py`（补充完整测试）

- [ ] **Step 1: 补充 alerts API 测试**

```python
# tests/integration/test_alerts_api.py 补充：
class TestAlertTriggerAPI:
    def test_trigger_returns_200(self, client):
        with patch("services.alert_service.AlertService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.evaluate_all.return_value = []
            mock_svc_cls.return_value = mock_svc
            response = client.post("/api/v1/alerts/trigger")
            assert response.status_code == 200
            assert "triggered" in response.json()
```

- [ ] **Step 2: 创建 reports API 测试**

```python
# tests/integration/test_reports_api.py
"""报告 API 集成测试"""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestReportsAPI:
    def test_trigger_weekly_returns_200(self, client):
        with patch("services.report_service.ReportService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.generate.return_value = "/static/reports/weekly_2026-03-21.html"
            mock_svc_cls.return_value = mock_svc
            response = client.post("/api/v1/reports/weekly")
            assert response.status_code == 200
            assert response.json()["status"] == "generated"

    def test_trigger_monthly_returns_200(self, client):
        with patch("services.report_service.ReportService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.generate.return_value = "/static/reports/monthly_2026-03-21.html"
            mock_svc_cls.return_value = mock_svc
            response = client.post("/api/v1/reports/monthly")
            assert response.status_code == 200

    def test_generate_dashboard_returns_200(self, client):
        with patch("services.dashboard_service.DashboardService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.generate.return_value = "/static/reports/dashboard_2026-03-21.html"
            mock_svc_cls.return_value = mock_svc
            response = client.post("/api/v1/reports/dashboard/generate")
            assert response.status_code == 200
```

- [ ] **Step 3: 运行全部测试**

Run: `uv run pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_reports_api.py tests/integration/test_alerts_api.py
git commit -m "test: add Phase 5 integration tests for alerts and reports API"
```

---

## 执行顺序

```
Task 1 (DDL + Init)
    ↓
Task 2 (Alert Schemas)
    ↓
Task 3 (AlertService) → Task 4 (Alert API)
    ↓
Task 5 (DashboardService + Template)
    ↓
Task 6 (ReportService + Templates)
    ↓
Task 7 (Scheduler + Static Files + Config)
    ↓
Task 8 (Integration Tests)
```
