import pytest
from starlette.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_returns_components(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "components" in data
    assert "clickhouse" in data["components"]
    assert "ollama" in data["components"]
