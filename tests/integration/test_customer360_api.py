# tests/integration/test_customer360_api.py
"""客户360 API 集成测试"""
import os
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.config import get_settings
from api.dependencies import get_customer360_service
from schemas.customer360 import (
    Customer360Summary,
    CustomerDistribution,
    CustomerTrend,
    CustomerMergeQueue,
    MatchResult,
    RawCustomer,
    MatchAction,
)
from tests.conftest import TEST_API_KEY


@pytest.fixture
def mock_customer360_service():
    """返回一个预配置好的模拟 Customer360Service"""
    mock = MagicMock()
    return mock


@pytest.fixture
def client(mock_customer360_service):
    """TestClient with scheduler and service mocked"""
    os.environ["API_KEYS"] = TEST_API_KEY
    get_settings.cache_clear()
    with patch("services.scheduler_service.start_scheduler"), \
         patch("services.scheduler_service.stop_scheduler"):
        app = create_app()
        app.dependency_overrides[get_customer360_service] = lambda: mock_customer360_service
        yield TestClient(app, headers={"X-API-Key": TEST_API_KEY})
        app.dependency_overrides.clear()


class TestCustomer360SummaryAPI:
    def test_get_summary_returns_200(self, client, mock_customer360_service):
        mock_customer360_service.get_summary.return_value = Customer360Summary(
            total_customers=100,
            merged_customers=5,
            pending_merges=2,
            ar_total=Decimal("1000000.00"),
            ar_overdue_total=Decimal("50000.00"),
            overall_overdue_rate=5.0,
            risk_distribution={"高": 3, "中": 10, "低": 87},
            concentration_top10_ratio=0.35,
            top10_ar_customers=[],
        )
        response = client.get("/api/v1/customer360/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_customers"] == 100
        assert data["merged_customers"] == 5
        assert data["ar_total"] == "1000000.00"
        assert data["risk_distribution"] == {"高": 3, "中": 10, "低": 87}
        mock_customer360_service.get_summary.assert_called_once()

    def test_get_summary_default_date(self, client, mock_customer360_service):
        mock_customer360_service.get_summary.return_value = Customer360Summary(
            total_customers=0,
            merged_customers=0,
            pending_merges=0,
            ar_total=Decimal("0"),
            ar_overdue_total=Decimal("0"),
            overall_overdue_rate=0.0,
            risk_distribution={},
            concentration_top10_ratio=0.0,
            top10_ar_customers=[],
        )
        response = client.get("/api/v1/customer360/summary")
        assert response.status_code == 200


class TestCustomer360DistributionAPI:
    def test_get_distribution_returns_200(self, client, mock_customer360_service):
        mock_customer360_service.get_distribution.return_value = CustomerDistribution(
            by_company=[{"company": "C001", "count": 50, "ar_total": 500000.0}],
            by_risk_level=[{"risk": "低", "count": 40, "ar_total": 400000.0}],
            by_overdue_bucket=[{"bucket": "0-30天", "count": 30, "amount": 300000.0}],
        )
        response = client.get("/api/v1/customer360/distribution")
        assert response.status_code == 200
        data = response.json()
        assert "by_company" in data
        assert "by_risk_level" in data
        assert "by_overdue_bucket" in data
        mock_customer360_service.get_distribution.assert_called_once()

    def test_get_distribution_with_stat_date(self, client, mock_customer360_service):
        mock_customer360_service.get_distribution.return_value = CustomerDistribution(
            by_company=[],
            by_risk_level=[],
            by_overdue_bucket=[],
        )
        response = client.get("/api/v1/customer360/distribution?stat_date=2026-03-01")
        assert response.status_code == 200
        mock_customer360_service.get_distribution.assert_called_once()

    def test_get_distribution_invalid_date(self, client, mock_customer360_service):
        response = client.get("/api/v1/customer360/distribution?stat_date=invalid-date")
        assert response.status_code == 400
        assert "无效的日期格式" in response.json()["error"]["message"]


class TestCustomer360TrendAPI:
    def test_get_trend_returns_200(self, client, mock_customer360_service):
        mock_customer360_service.get_trend.return_value = CustomerTrend(
            dates=["202601", "202602"],
            customer_counts=[80, 100],
            ar_totals=[800000.0, 1000000.0],
            overdue_rates=[0.05, 0.03],
        )
        response = client.get("/api/v1/customer360/trend")
        assert response.status_code == 200
        data = response.json()
        assert data["dates"] == ["202601", "202602"]
        assert data["customer_counts"] == [80, 100]
        mock_customer360_service.get_trend.assert_called_once_with(12)

    def test_get_trend_custom_months(self, client, mock_customer360_service):
        mock_customer360_service.get_trend.return_value = CustomerTrend(
            dates=["202501", "202502"],
            customer_counts=[50, 60],
            ar_totals=[500000.0, 600000.0],
            overdue_rates=[0.02, 0.01],
        )
        response = client.get("/api/v1/customer360/trend?months=6")
        assert response.status_code == 200
        mock_customer360_service.get_trend.assert_called_once_with(6)

    def test_get_trend_months_out_of_range(self, client, mock_customer360_service):
        response = client.get("/api/v1/customer360/trend?months=100")
        assert response.status_code == 422  # Pydantic validation error


class TestCustomer360DetailAPI:
    def test_get_detail_returns_200(self, client, mock_customer360_service):
        mock_customer360_service.get_customer_detail.return_value = {
            "unified_customer_code": "C360_TEST",
            "customer_name": "测试客户",
            "ar_total": "500000.00",
        }
        response = client.get("/api/v1/customer360/C360_TEST/detail")
        assert response.status_code == 200
        data = response.json()
        assert data["unified_customer_code"] == "C360_TEST"
        mock_customer360_service.get_customer_detail.assert_called_once_with("C360_TEST")

    def test_get_detail_not_found(self, client, mock_customer360_service):
        mock_customer360_service.get_customer_detail.return_value = {}
        response = client.get("/api/v1/customer360/NONEXISTENT/detail")
        assert response.status_code == 404
        assert "客户不存在" in response.json()["error"]["message"]


class TestMergeQueueAPI:
    def test_get_merge_queue_returns_200(self, client, mock_customer360_service):
        mock_customer360_service.get_merge_queue.return_value = []
        response = client.get("/api/v1/customer360/merge-queue?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["items"] == []
        mock_customer360_service.get_merge_queue.assert_called_once_with("pending")

    def test_get_merge_queue_with_items(self, client, mock_customer360_service):
        mock_queue_item = CustomerMergeQueue(
            id="mq_001",
            match_result=MatchResult(
                action=MatchAction.PENDING,
                customers=[
                    RawCustomer(
                        source_system="kingdee",
                        customer_id="K001",
                        customer_name="腾讯科技",
                    ),
                    RawCustomer(
                        source_system="kingdee",
                        customer_id="K002",
                        customer_name="腾讯科技（深圳）",
                    ),
                ],
                unified_customer_code="C360_T001",
                similarity=0.91,
                reason="名称相似度 0.91",
            ),
            status="pending",
        )
        mock_customer360_service.get_merge_queue.return_value = [mock_queue_item]
        response = client.get("/api/v1/customer360/merge-queue?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == "mq_001"
        assert data["items"][0]["similarity"] == 0.91
        assert data["items"][0]["status"] == "pending"
        assert len(data["items"][0]["customers"]) == 2


class TestMergeQueueConfirmAPI:
    def test_confirm_merge_returns_200(self, client, mock_customer360_service):
        mock_customer360_service.confirm_merge.return_value = {
            "id": "mq_001",
            "status": "confirmed",
            "unified_customer_code": "C360_T001",
            "operator": "api",
        }
        response = client.post("/api/v1/customer360/merge-queue/mq_001/confirm")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "mq_001"
        assert data["status"] == "confirmed"
        mock_customer360_service.confirm_merge.assert_called_once_with("mq_001")


class TestMergeQueueRejectAPI:
    def test_reject_merge_returns_200(self, client, mock_customer360_service):
        mock_customer360_service.reject_merge.return_value = {
            "id": "mq_002",
            "status": "rejected",
            "operator": "api",
        }
        response = client.post("/api/v1/customer360/merge-queue/mq_002/reject")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "mq_002"
        assert data["status"] == "rejected"
        mock_customer360_service.reject_merge.assert_called_once_with("mq_002")


class TestCustomer360UndoAPI:
    def test_undo_merge_returns_200(self, client, mock_customer360_service):
        mock_customer360_service.undo_merge.return_value = {
            "customer_code": "C360_T001",
            "original_customer_id": "K001",
            "status": "undone",
            "reason": "测试撤销",
        }
        response = client.post(
            "/api/v1/customer360/C360_T001/undo",
            json={"original_customer_id": "K001", "reason": "测试撤销"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["customer_code"] == "C360_T001"
        assert data["original_customer_id"] == "K001"
        assert data["status"] == "undone"
        mock_customer360_service.undo_merge.assert_called_once_with(
            unified_customer_code="C360_T001",
            original_customer_id="K001",
            reason="测试撤销",
        )

    def test_undo_merge_without_reason(self, client, mock_customer360_service):
        mock_customer360_service.undo_merge.return_value = {
            "customer_code": "C360_T002",
            "original_customer_id": "K002",
            "status": "undone",
            "reason": "",
        }
        response = client.post(
            "/api/v1/customer360/C360_T002/undo",
            json={"original_customer_id": "K002"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "undone"
        mock_customer360_service.undo_merge.assert_called_once_with(
            unified_customer_code="C360_T002",
            original_customer_id="K002",
            reason="",
        )


class TestCustomer360AttributionAPI:
    def test_get_attribution_returns_200(self, client, mock_customer360_service):
        mock_customer360_service.get_attribution_data.return_value = {
            "dimension": "company",
            "data": [
                {"company": "C001", "ar_change": 50000.0, "change_rate": 0.05},
                {"company": "C002", "ar_change": -20000.0, "change_rate": -0.02},
            ],
        }
        response = client.get(
            "/api/v1/customer360/attribution?start_date=2026-01-01&end_date=2026-03-01"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dimension"] == "company"
        assert len(data["data"]) == 2
        mock_customer360_service.get_attribution_data.assert_called_once()

    def test_get_attribution_missing_params(self, client, mock_customer360_service):
        response = client.get("/api/v1/customer360/attribution")
        assert response.status_code == 422  # missing required query params

    def test_get_attribution_invalid_date_format(self, client, mock_customer360_service):
        response = client.get(
            "/api/v1/customer360/attribution?start_date=invalid&end_date=2026-03-01"
        )
        assert response.status_code == 400
        assert "无效的日期格式" in response.json()["error"]["message"]
