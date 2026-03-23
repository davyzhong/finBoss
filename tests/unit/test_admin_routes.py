"""Admin routes integration tests."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock


@pytest.fixture
def test_app():
    """Create app and patch AuthMiddleware to allow test requests through."""
    from api.main import create_app

    app = create_app()

    async def mock_auth_middleware_call(self, scope, receive, send):
        """Bypass API-key auth and set a mock admin user in request state."""
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["user"] = {"user_id": "u_test", "role": "admin", "name": "Test Admin"}
        await self.app(scope, receive, send)

    # Apply middleware patch before any requests
    admin_mw_patch = patch(
        "api.middleware.auth.AuthMiddleware.__call__", mock_auth_middleware_call
    )
    admin_mw_patch.start()
    try:
        yield app
    finally:
        admin_mw_patch.stop()


@pytest.fixture
def mock_user_service():
    """Mock UserService methods for tests that don't need real DB access."""
    with patch("api.routes.admin.UserService") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_users_returns_200(test_app, mock_user_service):
    """GET /admin/users returns 200 and a list of users for admin."""
    mock_user_service.list_users.return_value = [
        {
            "user_id": "u123",
            "external_id": "ext1",
            "provider": "feishu",
            "name": "Test User",
            "email": "test@example.com",
            "role": "finance",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00",
        }
    ]
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as ac:
        resp = await ac.get("/admin/users")
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert len(data["users"]) == 1
    assert data["users"][0]["user_id"] == "u123"
    mock_user_service.list_users.assert_called_once()


@pytest.mark.asyncio
async def test_list_users_empty_list(test_app, mock_user_service):
    """GET /admin/users returns an empty list when no users exist."""
    mock_user_service.list_users.return_value = []
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as ac:
        resp = await ac.get("/admin/users")
    assert resp.status_code == 200
    data = resp.json()
    assert data["users"] == []


@pytest.mark.asyncio
async def test_update_user_role_returns_success(test_app, mock_user_service):
    """PUT /admin/users/{id}/role returns 200 with correct body."""
    mock_user_service.update_user_role.return_value = True
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as ac:
        resp = await ac.put(
            "/admin/users/u123/role",
            json={"role": "sales_manager"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["user_id"] == "u123"
    assert data["role"] == "sales_manager"
    mock_user_service.update_user_role.assert_called_once_with("u123", "sales_manager")


@pytest.mark.asyncio
async def test_list_roles_returns_roles(test_app, mock_user_service):
    """GET /admin/roles returns the list of available roles."""
    mock_user_service.list_roles.return_value = [
        {"role_id": "admin", "role_name": "管理员", "desc": "系统管理员"},
        {"role_id": "finance", "role_name": "财务", "desc": "财务人员"},
    ]
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as ac:
        resp = await ac.get("/admin/roles")
    assert resp.status_code == 200
    data = resp.json()
    assert "roles" in data
    assert len(data["roles"]) == 2
    assert data["roles"][0]["role_id"] == "admin"
    mock_user_service.list_roles.assert_called_once()


@pytest.mark.asyncio
async def test_require_admin_raises_403_for_non_admin(test_app):
    """When _require_admin finds a non-admin role, it raises 403."""

    async def mock_auth_non_admin(self, scope, receive, send):
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["user"] = {"user_id": "u999", "role": "finance"}
        await self.app(scope, receive, send)

    non_admin_patch = patch(
        "api.middleware.auth.AuthMiddleware.__call__", mock_auth_non_admin
    )
    non_admin_patch.start()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/admin/users")
    finally:
        non_admin_patch.stop()

    assert resp.status_code == 403
    data = resp.json()
    assert "需要管理员权限" in data["error"]["message"]


@pytest.mark.asyncio
async def test_require_admin_raises_401_when_no_user(test_app):
    """When request.state.user is absent, _require_admin raises 401."""

    async def mock_auth_no_user(self, scope, receive, send):
        if "state" not in scope:
            scope["state"] = {}
        # Do NOT set scope["state"]["user"]
        await self.app(scope, receive, send)

    no_user_patch = patch(
        "api.middleware.auth.AuthMiddleware.__call__", mock_auth_no_user
    )
    no_user_patch.start()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://test",
        ) as ac:
            resp = await ac.get("/admin/users")
    finally:
        no_user_patch.stop()

    assert resp.status_code == 401
    data = resp.json()
    assert "请先登录" in data["error"]["message"]
