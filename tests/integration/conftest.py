# tests/integration/conftest.py
"""Integration test fixtures - middleware bypass applied globally here."""
from unittest.mock import patch

import pytest

from api.middleware.auth import AuthMiddleware
from api.middleware.session import SessionMiddleware


@pytest.fixture(autouse=True)
def bypass_middlewares():
    """Bypass Auth + Session middlewares for all integration tests."""
    async def fake_call(self, scope, receive, send):
        await self.app(scope, receive, send)

    with patch.object(AuthMiddleware, "__call__", fake_call), \
         patch.object(SessionMiddleware, "__call__", fake_call):
        yield
