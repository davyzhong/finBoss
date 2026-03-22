"""预警 API 集成测试"""
import os
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.config import get_settings
from api.dependencies import get_alert_service
from tests.conftest import TEST_API_KEY


class MockAlertService:
    """Mock AlertService for testing"""

    def __init__(self):
        self.list_rules_mock = MagicMock(return_value=[])
        self.create_rule_mock = MagicMock(return_value="new_rule")
        self.update_rule_mock = MagicMock(return_value=None)
        self.delete_rule_mock = MagicMock(return_value=True)
        self.get_history_mock = MagicMock(return_value=[])
        self.evaluate_all_mock = MagicMock(return_value=[])

    def list_rules(self):
        return self.list_rules_mock()

    def create_rule(self, data):
        return self.create_rule_mock(data)

    def update_rule(self, rule_id, data):
        return self.update_rule_mock(rule_id, data)

    def delete_rule(self, rule_id):
        return self.delete_rule_mock(rule_id)

    def get_history(self, limit=100):
        return self.get_history_mock(limit=limit)

    def evaluate_all(self):
        return self.evaluate_all_mock()


@pytest.fixture
def mock_client():
    """带 Mock AlertService 的测试客户端"""
    os.environ["API_KEYS"] = TEST_API_KEY
    get_settings.cache_clear()
    mock_svc = MockAlertService()
    app = create_app()
    app.dependency_overrides[get_alert_service] = lambda: mock_svc
    client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
    client.mock_svc = mock_svc
    yield client
    app.dependency_overrides.clear()


class TestAlertRulesAPI:
    def test_list_rules_returns_200(self, mock_client):
        response = mock_client.get("/api/v1/alerts/rules")
        assert response.status_code == 200
        mock_client.mock_svc.list_rules_mock.assert_called_once()

    def test_create_rule_returns_200(self, mock_client):
        response = mock_client.post(
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
        data = response.json()
        assert data["status"] == "created"
        mock_client.mock_svc.create_rule_mock.assert_called_once()

    def test_delete_rule_returns_200(self, mock_client):
        response = mock_client.delete("/api/v1/alerts/rules/test_rule")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        mock_client.mock_svc.delete_rule_mock.assert_called_once_with("test_rule")

    def test_get_history_returns_200(self, mock_client):
        response = mock_client.get("/api/v1/alerts/history")
        assert response.status_code == 200
        mock_client.mock_svc.get_history_mock.assert_called_once()

    def test_trigger_returns_200(self, mock_client):
        response = mock_client.post("/api/v1/alerts/trigger")
        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] == 0
        mock_client.mock_svc.evaluate_all_mock.assert_called_once()
