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
                "risk_high_count": 3,
                "total_customers": 100,
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
            assert path.endswith(".html")

    def test_yoy_method_exists(self):
        service = ReportService()
        assert hasattr(service, "_get_yoy_change")
