# tests/integration/test_api.py
"""API 集成测试"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def mock_data_service():
    with patch("api.routes.ar.get_data_service") as mock:
        svc = MagicMock()
        svc.get_ar_summary.return_value = []
        svc.get_ar_detail.return_value = []
        svc.get_customer_ar.return_value = []
        mock.return_value = svc
        yield svc


@pytest.fixture
def mock_quality_service():
    with patch("api.routes.ar.get_quality_service") as mock:
        from services.quality_service import QualityService
        mock.return_value = QualityService()
        yield mock


@pytest.fixture
def client():
    return TestClient(create_app())


class TestHealthEndpoint:
    def test_health_check(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"


class TestAREndpoints:
    def test_get_ar_summary(self, client, mock_data_service):
        mock_data_service.get_ar_summary.return_value = [
            {
                "stat_date": datetime.now().isoformat(),
                "company_code": "C001", "company_name": "测试公司",
                "total_ar_amount": 1000000.0, "received_amount": 300000.0,
                "allocated_amount": 200000.0, "unallocated_amount": 500000.0,
                "overdue_amount": 100000.0, "overdue_count": 5, "total_count": 20,
                "overdue_rate": 0.25,
                "aging_0_30": 200000.0, "aging_31_60": 150000.0,
                "aging_61_90": 100000.0, "aging_91_180": 50000.0, "aging_180_plus": 0.0,
                "etl_time": datetime.now().isoformat(),
            }
        ]
        r = client.get("/api/v1/ar/summary")
        assert r.status_code == 200
        assert r.json()[0]["company_code"] == "C001"

    def test_get_ar_summary_with_filters(self, client, mock_data_service):
        r = client.get("/api/v1/ar/summary", params={"company_code": "C001"})
        assert r.status_code == 200
        mock_data_service.get_ar_summary.assert_called_once_with(company_code="C001", stat_date=None)

    def test_get_customer_ar(self, client, mock_data_service):
        mock_data_service.get_customer_ar.return_value = []
        r = client.get("/api/v1/ar/customer", params={"is_overdue": True, "limit": 50})
        assert r.status_code == 200
        mock_data_service.get_customer_ar.assert_called_once_with(customer_code=None, is_overdue=True, limit=50)

    def test_quality_check(self, client, mock_data_service, mock_quality_service):
        r = client.post("/api/v1/ar/quality-check", json={"table_name": "std_ar", "max_delay_minutes": 10})
        assert r.status_code == 200
        assert "pass_rate" in r.json()


class TestQueryEndpoints:
    def test_execute_select_query(self, client, mock_data_service):
        mock_data_service.execute_query.return_value = [{"id": 1}]
        r = client.post("/api/v1/query/execute", json={"sql": "SELECT * FROM test"})
        assert r.status_code == 200
        assert "data" in r.json()

    def test_execute_non_select_rejected(self, client):
        r = client.post("/api/v1/query/execute", json={"sql": "DROP TABLE test"})
        assert r.status_code == 400
        assert "SELECT" in r.json()["detail"]

    def test_execute_insert_rejected(self, client):
        r = client.post("/api/v1/query/execute", json={"sql": "INSERT INTO test VALUES (1)"})
        assert r.status_code == 400
