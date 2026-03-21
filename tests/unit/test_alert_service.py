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
            # First call: no rules in DB → fall back to BUILTIN_RULES
            # Subsequent calls: metric query returns the value
            mock_ch.execute_query.side_effect = [
                [],  # rules query → empty, use BUILTIN_RULES
                [{"overdue_rate": 0.45}],  # overdue_rate query
            ]
            service = AlertService()
            alerts = service.evaluate_all()
            assert len(alerts) >= 1

    def test_evaluate_threshold_not_exceeded(self):
        with patch("services.alert_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            # First call: no rules in DB → fall back to BUILTIN_RULES
            # Subsequent calls: metric query returns value below threshold
            mock_ch.execute_query.side_effect = [
                [],  # rules query → empty, use BUILTIN_RULES
                [{"overdue_rate": 0.1}],  # 0.1 < 0.3 → not exceeded
            ]
            service = AlertService()
            alerts = service.evaluate_all()
            overdue_rate_alerts = [a for a in alerts if a.rule_id == "rule_overdue_rate"]
            assert len(overdue_rate_alerts) == 0

    def test_is_exceeded_gt(self):
        service = AlertService()
        assert service._is_exceeded(0.45, "gt", 0.3) is True
        assert service._is_exceeded(0.1, "gt", 0.3) is False

    def test_is_exceeded_gte(self):
        service = AlertService()
        assert service._is_exceeded(0.3, "gte", 0.3) is True
        assert service._is_exceeded(0.29, "gte", 0.3) is False
