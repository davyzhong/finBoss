"""报告 API 集成测试"""
import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.config import get_settings
from api.routes.reports import get_dashboard_service, get_report_service
from tests.conftest import TEST_API_KEY


class MockReportService:
    """Mock ReportService for testing"""

    def __init__(self):
        self.generate_mock = MagicMock(return_value="/static/reports/weekly_2026-03-21.html")
        self._ch = MagicMock()
        self._ch.execute_query = MagicMock(return_value=[])

    def generate(self, report_type: str):
        return self.generate_mock(report_type)


class MockDashboardService:
    """Mock DashboardService for testing"""

    def __init__(self):
        self.generate_mock = MagicMock(return_value="/static/reports/dashboard_2026-03-21.html")

    def generate(self):
        return self.generate_mock()


@pytest.fixture
def mock_report_client():
    """带 Mock ReportService 的测试客户端"""
    os.environ["API_KEYS"] = TEST_API_KEY
    get_settings.cache_clear()
    mock_svc = MockReportService()
    app = create_app()
    app.dependency_overrides[get_report_service] = lambda: mock_svc
    client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
    client.mock_svc = mock_svc
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_dashboard_client():
    """带 Mock DashboardService 的测试客户端"""
    os.environ["API_KEYS"] = TEST_API_KEY
    get_settings.cache_clear()
    mock_svc = MockDashboardService()
    app = create_app()
    app.dependency_overrides[get_dashboard_service] = lambda: mock_svc
    client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
    client.mock_svc = mock_svc
    yield client
    app.dependency_overrides.clear()


class TestReportsAPI:
    def test_trigger_weekly_returns_200(self, mock_report_client):
        response = mock_report_client.post("/api/v1/reports/weekly")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "generated"
        mock_report_client.mock_svc.generate_mock.assert_called_once_with("weekly")

    def test_trigger_monthly_returns_200(self, mock_report_client):
        response = mock_report_client.post("/api/v1/reports/monthly")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "generated"
        mock_report_client.mock_svc.generate_mock.assert_called_once_with("monthly")

    def test_list_records_returns_200(self, mock_report_client):
        response = mock_report_client.get("/api/v1/reports/records")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data


class TestDashboardAPI:
    def test_generate_dashboard_returns_200(self, mock_dashboard_client):
        response = mock_dashboard_client.post("/api/v1/reports/dashboard/generate")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "generated"
        mock_dashboard_client.mock_svc.generate_mock.assert_called_once()
