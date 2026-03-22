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


class TestAggregatedAnomalies:
    def test_group_by_table(self):
        from services.field_quality_service import FieldQualityService
        with patch.object(FieldQualityService, "__init__", lambda self, ch=None: None):
            svc = FieldQualityService()
            svc._ch = MagicMock()
            svc._ch.execute_query.return_value = [
                {"id": "1", "table_name": "std.std_ar", "column_name": "ar_amount",
                 "metric": "null_rate", "value": 0.3, "threshold": 0.2,
                 "severity": "高", "status": "open", "assignee": "zhang",
                 "detected_at": datetime.now()},
                {"id": "2", "table_name": "std.std_ar", "column_name": "due_date",
                 "metric": "null_rate", "value": 0.25, "threshold": 0.2,
                 "severity": "中", "status": "open", "assignee": "",
                 "detected_at": datetime.now()},
                {"id": "3", "table_name": "dm.dm_customer360", "column_name": "ar_overdue",
                 "metric": "null_rate", "value": 0.15, "threshold": 0.2,
                 "severity": "低", "status": "open", "assignee": "li",
                 "detected_at": datetime.now()},
            ]
            result = svc.get_aggregated_anomalies(group_by=["table"])
            assert result["total_anomalies"] == 3
            keys = {g["key"] for g in result["groups"]}
            assert "std.std_ar" in keys
            assert "dm.dm_customer360" in keys
            std_ar_group = next(g for g in result["groups"] if g["key"] == "std.std_ar")
            assert std_ar_group["total"] == 2
            assert std_ar_group["高"] == 1
            assert std_ar_group["中"] == 1
            assert std_ar_group["unassigned"] == 1

    def test_group_by_assignee(self):
        from services.field_quality_service import FieldQualityService
        with patch.object(FieldQualityService, "__init__", lambda self, ch=None: None):
            svc = FieldQualityService()
            svc._ch = MagicMock()
            svc._ch.execute_query.return_value = [
                {"id": "1", "table_name": "std.std_ar", "column_name": "ar_amount",
                 "metric": "null_rate", "value": 0.3, "threshold": 0.2,
                 "severity": "高", "status": "open", "assignee": "zhang",
                 "detected_at": datetime.now()},
                {"id": "2", "table_name": "std.std_ar", "column_name": "due_date",
                 "metric": "null_rate", "value": 0.25, "threshold": 0.2,
                 "severity": "中", "status": "open", "assignee": "zhang",
                 "detected_at": datetime.now()},
            ]
            result = svc.get_aggregated_anomalies(group_by=["assignee"])
            zhang_group = next(g for g in result["groups"] if g["key"] == "zhang")
            assert zhang_group["total"] == 2

    def test_empty_result(self):
        from services.field_quality_service import FieldQualityService
        with patch.object(FieldQualityService, "__init__", lambda self, ch=None: None):
            svc = FieldQualityService()
            svc._ch = MagicMock()
            svc._ch.execute_query.return_value = []
            result = svc.get_aggregated_anomalies(group_by=["table"])
            assert result["groups"] == []
            assert result["total_anomalies"] == 0
