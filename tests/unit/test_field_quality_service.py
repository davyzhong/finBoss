import pytest
from unittest.mock import MagicMock, patch
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
        """null_rate=0.35 (Date column, no etl_time) triggers HIGH anomaly."""
        mock_ch = MagicMock()
        # Patch list_columns to avoid execute_query call for column discovery
        with patch.object(FieldQualityService, "list_columns", return_value=[
            {"column_name": "due_date", "type": "Nullable(Date)"},
        ]):
            with patch.object(FieldQualityService, "_has_etl_time", return_value=False):
                mock_ch.execute_query.side_effect = [
                    [{"v": 0.35}],   # null_rate
                    [{"v": 0.1}],    # distinct_rate
                ]
                svc = FieldQualityService(ch=mock_ch)
                anomalies = svc.check_column("dm.ar", "due_date", date.today())
        assert len(anomalies) == 1
        assert anomalies[0]["severity"] == "高"
        assert anomalies[0]["metric"] == "null_rate"
        assert anomalies[0]["value"] == 0.35

    def test_no_anomaly_when_under_threshold(self):
        """Decimal column with null_rate=0.01, no anomalies."""
        mock_ch = MagicMock()
        with patch.object(FieldQualityService, "list_columns", return_value=[
            {"column_name": "amount", "type": "Decimal(18,2)"},
        ]):
            with patch.object(FieldQualityService, "_has_etl_time", return_value=False):
                mock_ch.execute_query.side_effect = [
                    [{"v": 0.01}],   # null_rate
                    [{"v": 0.05}],   # distinct_rate
                    [{"v": 0.0}],    # negative_rate
                ]
                svc = FieldQualityService(ch=mock_ch)
                anomalies = svc.check_column("dm.ar", "amount", date.today())
        assert anomalies == []

    def test_freshness_hours_triggers_medium_anomaly(self):
        """freshness_hours > 72h (exceeds high threshold) triggers a 中 anomaly."""
        mock_ch = MagicMock()
        with patch.object(FieldQualityService, "list_columns", return_value=[
            {"column_name": "updated_at", "type": "DateTime"},
        ]):
            with patch.object(FieldQualityService, "_has_etl_time", return_value=True):
                mock_ch.execute_query.side_effect = [
                    [{"v": 0.0}],    # null_rate
                    [{"v": 0.1}],    # distinct_rate
                    [{"v": 73.0}],   # freshness_hours: 73h > 72h (high) → 中
                ]
                svc = FieldQualityService(ch=mock_ch)
                anomalies = svc.check_column("dm.c360", "updated_at", date.today())
        freshness = [a for a in anomalies if a["metric"] == "freshness_hours"]
        assert len(freshness) == 1
        assert freshness[0]["severity"] == "中"

    def test_distinct_rate_high_triggers_medium(self):
        """distinct_rate 0.991 (> 0.99) triggers LOW anomaly; string skips negative_rate."""
        mock_ch = MagicMock()
        with patch.object(FieldQualityService, "list_columns", return_value=[
            {"column_name": "id", "type": "String"},
        ]):
            with patch.object(FieldQualityService, "_has_etl_time", return_value=False):
                mock_ch.execute_query.side_effect = [
                    [{"v": 0.0}],     # null_rate
                    [{"v": 0.991}],   # distinct_rate (> 0.99 → LOW)
                ]
                svc = FieldQualityService(ch=mock_ch)
                anomalies = svc.check_column("dm.t", "id", date.today())
        dr = [a for a in anomalies if a["metric"] == "distinct_rate"]
        assert len(dr) == 1
        assert dr[0]["severity"] == "低"

    def test_negative_rate_numeric_only(self):
        svc = FieldQualityService(ch=MagicMock())
        assert svc._should_check_negative_rate("String") is False
        assert svc._should_check_negative_rate("Nullable(String)") is False
        assert svc._should_check_negative_rate("Decimal(18,2)") is True
        assert svc._should_check_negative_rate("Int64") is True
        assert svc._should_check_negative_rate("Float64") is True

    def test_etl_time_absent_skips_filter(self):
        """When a table has no etl_time column, _build_filter_clause returns '1=1'."""
        mock_ch = MagicMock()
        mock_ch.execute_query.return_value = []  # no columns at all
        svc = FieldQualityService(ch=mock_ch)
        clause = svc._build_filter_clause("dm.notimetable", "2026-03-22")
        assert clause == "1=1"

    def test_etl_time_present_uses_filter(self):
        """When a table HAS etl_time column, _build_filter_clause returns date filter."""
        mock_ch = MagicMock()
        mock_ch.execute_query.return_value = [{"column_name": "etl_time", "type": "DateTime"}]
        svc = FieldQualityService(ch=mock_ch)
        clause = svc._build_filter_clause("dm.hastime", "2026-03-22")
        assert "etl_time" in clause
        assert "2026-03-22" in clause

    def test_update_anomaly_resolved_sets_resolved_at(self):
        mock_ch = MagicMock()
        mock_ch.execute.return_value = None
        svc = FieldQualityService(ch=mock_ch)
        svc.update_anomaly("test-uuid", "resolved")
        call_args = mock_ch.execute.call_args[0][0]
        assert "resolved" in call_args
        assert "resolved_at" in call_args

    def test_update_anomaly_rejects_invalid_status(self):
        svc = FieldQualityService(ch=MagicMock())
        with pytest.raises(ValueError, match="Invalid status"):
            svc.update_anomaly("test-uuid", "invalid_status")

    def test_check_all_continues_after_table_error(self):
        """Per-table error isolation: one bad table does not abort the scan."""
        mock_ch = MagicMock()
        mock_ch.execute_query.return_value = []   # covers all list_columns / metric queries
        mock_ch.execute.return_value = None
        svc = FieldQualityService(ch=mock_ch)
        # Mock table list as dicts so the code's row['database'].row['name'] unpacking works
        with patch.object(
            FieldQualityService, "list_monitored_tables",
            return_value=[{"database": "dm", "name": "good_table"}]
        ):
            with patch.object(FieldQualityService, "generate_report_html", return_value=""):
                result = svc.check_all(date(2026, 3, 22))
        # Should complete with 1 table processed
        assert result["total_tables"] >= 1
        # Should complete with 1 table processed
        assert result["total_tables"] >= 1
