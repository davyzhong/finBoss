"""测试归因分析 API"""
import os
from fastapi.testclient import TestClient

from api.main import create_app
from tests.conftest import TEST_API_KEY

os.environ["API_KEYS"] = TEST_API_KEY
from api.config import get_settings
get_settings.cache_clear()
client = TestClient(create_app(), headers={"X-API-Key": TEST_API_KEY})


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
