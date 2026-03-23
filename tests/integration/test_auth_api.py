import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.mark.asyncio
async def test_health_public_without_session():
    """健康检查端点无需认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ar_summary_reachable():
    """AR summary 路由可访问（SessionMiddleware bypass 允许请求通过）"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/api/v1/ar/summary")
    # Without middlewares, route is reached (returns 200 or 500 depending on DB)
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_admin_users_unauthorized_without_session():
    """Admin users 路由无 session 时返回 401"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/admin/users")
    # Admin route checks request.state.user directly; without session it raises 401
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_page_renders():
    """登录页显示提供商选择"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/auth/login")
    assert resp.status_code == 200
    assert "feishu" in resp.text.lower() or "飞书" in resp.text


@pytest.mark.asyncio
async def test_login_with_unknown_provider_returns_400():
    """无效的 provider 返回 400"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/auth/login", params={"provider": "unknown"})
    assert resp.status_code == 400
