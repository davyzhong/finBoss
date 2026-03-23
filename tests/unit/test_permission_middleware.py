from unittest.mock import MagicMock
from api.middleware.permission import PermissionMiddleware, ROLE_PERMISSIONS


def test_admin_can_access_all():
    assert ROLE_PERMISSIONS["admin"]["ar"]["read"] is True
    assert ROLE_PERMISSIONS["admin"]["ar"]["write"] is True
    assert ROLE_PERMISSIONS["admin"]["admin"]["write"] is True


def test_finance_cannot_write_ar():
    assert ROLE_PERMISSIONS["finance"]["ar"]["read"] is True
    assert ROLE_PERMISSIONS["finance"]["ar"]["write"] is False


def test_finance_cannot_access_admin():
    assert ROLE_PERMISSIONS["finance"]["admin"]["read"] is False
    assert ROLE_PERMISSIONS["finance"]["admin"]["write"] is False


def test_ops_cannot_access_ar():
    assert ROLE_PERMISSIONS["ops"]["ar"]["read"] is False
    assert ROLE_PERMISSIONS["ops"]["ar"]["write"] is False


def test_ops_can_write_reports():
    assert ROLE_PERMISSIONS["ops"]["reports"]["write"] is True


async def test_forbidden_returns_403():
    scope = {
        "type": "http",
        "path": "/api/v1/admin/config",
        "method": "PUT",
        "state": {"user": {"role": "finance", "name": "张三"}},
    }
    send_calls = []
    async def fake_send(msg):
        send_calls.append(msg)
    receive = MagicMock()
    middleware = PermissionMiddleware(app=MagicMock())
    await middleware(scope, receive, fake_send)
    assert any(c.get("status") == 403 for c in send_calls)
