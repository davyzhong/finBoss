"""API 集成测试"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services.clickhouse_service import ClickHouseDataService


class MockClickHouseService(ClickHouseDataService):
    """测试用 ClickHouse 服务 Mock"""

    def __init__(self):
        self._mock_get_ar_summary = MagicMock(return_value=[])
        self._mock_get_ar_detail = MagicMock(return_value=[])
        self._mock_get_customer_ar = MagicMock(return_value=[])
        self._mock_get_latest_etl_time = MagicMock(return_value=datetime(2026, 3, 21, 12, 0, 0))
        self._mock_execute_query = MagicMock(return_value=[])

    def get_ar_summary(self, company_code=None, stat_date=None):
        return self._mock_get_ar_summary(company_code=company_code, stat_date=stat_date)

    def get_ar_detail(self, bill_no=None, customer_code=None, company_code=None, is_overdue=None, limit=100):
        return self._mock_get_ar_detail(
            bill_no=bill_no, customer_code=customer_code,
            company_code=company_code, is_overdue=is_overdue, limit=limit,
        )

    def get_customer_ar(self, customer_code=None, is_overdue=None, limit=100):
        return self._mock_get_customer_ar(
            customer_code=customer_code, is_overdue=is_overdue, limit=limit,
        )

    def get_latest_etl_time(self, table_name):
        return self._mock_get_latest_etl_time(table_name=table_name)

    def execute_query(self, sql, params=None):
        return self._mock_execute_query(sql=sql, params=params)


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def mock_client():
    """带 Mock ClickHouse 服务的测试客户端"""
    from api.dependencies import get_clickhouse_service, get_quality_service

    mock_svc = MockClickHouseService()
    app = create_app()
    app.dependency_overrides[get_clickhouse_service] = lambda: mock_svc
    app.dependency_overrides[get_quality_service] = lambda: MagicMock()
    client = TestClient(app)
    client.mock_svc = mock_svc  # 给测试直接访问 mock 的途径
    yield client
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health_check(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"


class TestAREndpoints:
    def test_get_ar_summary(self, mock_client):
        mock_client.mock_svc._mock_get_ar_summary.return_value = [
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
        r = mock_client.get("/api/v1/ar/summary")
        assert r.status_code == 200
        assert r.json()[0]["company_code"] == "C001"

    def test_get_ar_summary_with_filters(self, mock_client):
        r = mock_client.get("/api/v1/ar/summary", params={"company_code": "C001"})
        assert r.status_code == 200
        mock_client.mock_svc._mock_get_ar_summary.assert_called_once_with(company_code="C001", stat_date=None)

    def test_get_customer_ar(self, mock_client):
        mock_client.mock_svc._mock_get_customer_ar.return_value = []
        r = mock_client.get("/api/v1/ar/customer", params={"is_overdue": True, "limit": 50})
        assert r.status_code == 200
        mock_client.mock_svc._mock_get_customer_ar.assert_called_once_with(
            customer_code=None, is_overdue=True, limit=50,
        )

    def test_quality_check(self, mock_client):
        r = mock_client.post("/api/v1/ar/quality-check", json={"table_name": "std_ar", "max_delay_minutes": 10})
        assert r.status_code == 200
        data = r.json()
        assert "passed" in data
        assert "total_rules" in data


class TestQueryEndpoints:
    def test_execute_select_query(self, mock_client):
        mock_client.mock_svc._mock_execute_query.return_value = [{"id": 1}]
        r = mock_client.post("/api/v1/query/execute", json={"sql": "SELECT * FROM test"})
        assert r.status_code == 200
        assert "data" in r.json()

    def test_execute_non_select_rejected(self, client):
        r = client.post("/api/v1/query/execute", json={"sql": "DROP TABLE test"})
        assert r.status_code == 400

    def test_execute_insert_rejected(self, client):
        r = client.post("/api/v1/query/execute", json={"sql": "INSERT INTO test VALUES (1)"})
        assert r.status_code == 400
