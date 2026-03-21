"""测试 DashboardService"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from services.dashboard_service import DashboardService


class TestDashboardService:
    def test_generate_creates_html_file(self):
        with patch("services.dashboard_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [{
                "ar_total": 1000000.0,
                "ar_overdue": 50000.0,
                "overdue_rate": 0.05,
                "customer_count": 100,
            }]
            service = DashboardService()
            path = service.generate()
            assert path is not None
            assert "dashboard" in path
            assert path.endswith(".html")

    def test_get_kpi_returns_dict(self):
        with patch("services.dashboard_service.ClickHouseDataService") as mock_ch_cls:
            mock_ch = MagicMock()
            mock_ch_cls.return_value = mock_ch
            mock_ch.execute_query.return_value = [{
                "ar_total": 1000000.0,
                "ar_overdue": 50000.0,
                "overdue_rate": 0.05,
                "customer_count": 100,
            }]
            service = DashboardService()
            kpi = service._get_kpi(date.today())
            assert kpi["ar_total"] == 1000000.0
            assert kpi["overdue_rate"] == 0.05
