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
                "content": f"**逾期预警日报 - {datetime.now().strftime('%Y-%m-%d')}**\n"
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

    def list_rules(self) -> list[dict]:
        """列出所有规则"""
        return self._ch.execute_query(
            "SELECT id, name, metric, operator, threshold, scope_type, scope_value, alert_level, enabled, created_at, updated_at "
            "FROM dm.alert_rules ORDER BY created_at DESC"
        )

    def create_rule(self, data: dict) -> str:
        """创建规则（INSERT 方式，ReplacingMergeTree 会自动去重）"""
        rule_id = data.get("id") or str(uuid.uuid4())
        now = datetime.now()
        try:
            self._ch.execute(
                "INSERT INTO dm.alert_rules (id, name, metric, operator, threshold, scope_type, scope_value, alert_level, enabled, created_at, updated_at) "
                "VALUES (%(id)s, %(name)s, %(metric)s, %(operator)s, %(threshold)s, %(scope_type)s, %(scope_value)s, %(alert_level)s, %(enabled)s, %(now)s, %(now)s)",
                {**data, "id": rule_id, "now": now}
            )
        except Exception:
            pass
        return rule_id

    def update_rule(self, rule_id: str, data: dict) -> None:
        """更新规则（INSERT 方式，ReplacingMergeTree 会替换同 id 的旧记录）"""
        now = datetime.now()
        data["updated_at"] = now
        data["id"] = rule_id
        try:
            self._ch.execute(
                "INSERT INTO dm.alert_rules (id, name, metric, operator, threshold, scope_type, scope_value, alert_level, enabled, created_at, updated_at) "
                "VALUES (%(id)s, %(name)s, %(metric)s, %(operator)s, %(threshold)s, %(scope_type)s, %(scope_value)s, %(alert_level)s, %(enabled)s, %(created_at)s, %(updated_at)s)",
                {
                    "id": rule_id,
                    "name": data.get("name"),
                    "metric": data.get("metric"),
                    "operator": data.get("operator"),
                    "threshold": data.get("threshold"),
                    "scope_type": data.get("scope_type"),
                    "scope_value": data.get("scope_value"),
                    "alert_level": data.get("alert_level"),
                    "enabled": data.get("enabled"),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        except Exception:
            pass

    def delete_rule(self, rule_id: str) -> bool:
        """删除规则（ClickHouse ReplacingMergeTree 不支持同步 DELETE，标记删除）"""
        # 由于 ClickHouse MergeTree 系列不支持同步 UPDATE/DELETE，
        # 暂通过 INSERT 一条 enabled=0 的记录标记软删除
        now = datetime.now()
        try:
            self._ch.execute(
                "INSERT INTO dm.alert_rules (id, name, metric, operator, threshold, scope_type, scope_value, alert_level, enabled, created_at, updated_at) "
                "VALUES (%(id)s, '', '', '', 0, '', '', '', 0, %(now)s, %(now)s)",
                {"id": rule_id, "now": now}
            )
            return True
        except Exception:
            return False

    def get_history(self, limit: int = 100) -> list[dict]:
        """查询预警历史"""
        return self._ch.execute_query(
            f"SELECT * FROM dm.alert_history ORDER BY triggered_at DESC LIMIT {limit}"
        )
