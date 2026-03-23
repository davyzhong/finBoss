# tests/integration/conftest.py
"""Integration test fixtures - session middleware bypass applied globally here."""
from unittest.mock import patch

import pytest

from api.middleware.session import SessionMiddleware


@pytest.fixture(autouse=True)
def bypass_session_middleware():
    """Bypass SessionMiddleware for all integration tests using API key auth."""
    async def fake_call(self, scope, receive, send):
        await self.app(scope, receive, send)

    with patch.object(SessionMiddleware, "__call__", fake_call):
        yield
