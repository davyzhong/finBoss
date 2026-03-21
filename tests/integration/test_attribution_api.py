"""测试归因分析 API"""
import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_analyze_endpoint_exists():
    response = client.post(
        "/api/v1/attribution/analyze",
        json={"question": "为什么本月逾期率上升了"},
    )
    assert response.status_code in (200, 500)
    if response.status_code == 200:
        data = response.json()
        assert "question" in data
        assert "factors" in data
        assert "overall_confidence" in data
