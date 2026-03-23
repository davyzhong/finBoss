import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock
from api.main import create_app


@pytest.fixture
def test_app():
    return create_app()


@pytest.mark.asyncio
async def test_login_without_provider_returns_providers_page(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/auth/login")
    assert resp.status_code == 200
    assert "feishu" in resp.text
    assert "dingtalk" in resp.text


@pytest.mark.asyncio
async def test_login_with_feishu_redirects(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/auth/login", params={"provider": "feishu"})
    assert resp.status_code == 302
    assert "open.feishu.cn" in resp.headers["location"]


@pytest.mark.asyncio
async def test_callback_unknown_provider_returns_400(test_app):
    # Unknown provider in the CSRF store -> state not found
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/auth/callback", params={"provider": "unknown", "state": "badstate", "code": "dummy"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "INVALID_PROVIDER"


@pytest.mark.asyncio
async def test_callback_missing_code_returns_400(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/auth/callback", params={"provider": "feishu"})
    assert resp.status_code == 400
