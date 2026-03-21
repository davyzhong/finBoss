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
