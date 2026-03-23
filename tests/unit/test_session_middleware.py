from unittest.mock import AsyncMock, MagicMock

import pytest

from api.middleware.session import PUBLIC_PATHS, SessionMiddleware, requires_auth


class TestPublicPaths:
    def test_public_paths_contains_expected_routes(self):
        assert "/health" in PUBLIC_PATHS
        assert "/auth/login" in PUBLIC_PATHS
        assert "/auth/callback" in PUBLIC_PATHS
        assert "/docs" in PUBLIC_PATHS


class TestRequiresAuth:
    def test_requires_auth_protected_path(self):
        assert requires_auth("/api/v1/ar/summary") is True

    def test_requires_auth_public_path_health(self):
        assert requires_auth("/health") is False

    def test_requires_auth_public_path_auth_login(self):
        assert requires_auth("/auth/login") is False

    def test_requires_auth_public_path_ai_health(self):
        assert requires_auth("/api/v1/ai/health") is False

    def test_requires_auth_public_path_docs(self):
        assert requires_auth("/docs") is False

    def test_requires_auth_public_path_redoc(self):
        assert requires_auth("/redoc") is False

    def test_requires_auth_public_path_openapi_json(self):
        assert requires_auth("/openapi.json") is False

    def test_requires_auth_public_path_feishu_events(self):
        assert requires_auth("/feishu/events") is False

    def test_requires_auth_public_path_ready(self):
        assert requires_auth("/ready") is False

    def test_requires_auth_sub_path_under_public(self):
        """Sub-path under a public path should also be public."""
        # /auth/login/anything should match /auth/login
        assert requires_auth("/auth/login/evil") is False
        assert requires_auth("/docs/something") is False


class TestSessionMiddleware:
    @pytest.fixture
    def store(self):
        from services.session_service import InMemorySessionStore

        return InMemorySessionStore()

    @pytest.fixture
    def middleware(self, store):
        return SessionMiddleware(app=AsyncMock(), session_store=store)

    async def test_session_injected_into_scope(self, store, middleware):
        """Valid session cookie injects user into scope state."""
        sid = store.create({"user_id": "u1", "role": "admin", "name": "test"})
        scope = {
            "type": "http",
            "path": "/api/v1/ar/summary",
            "headers": [(b"cookie", f"finboss_session={sid}".encode())],
            "state": {},
        }
        receive = MagicMock()
        send = AsyncMock()
        await middleware(scope, receive, send)
        assert scope["state"].get("user") is not None
        assert scope["state"]["user"]["user_id"] == "u1"
        assert scope["state"]["user"]["role"] == "admin"

    async def test_missing_session_redirects(self, middleware):
        """No session cookie on protected path redirects to /auth/login."""
        scope = {
            "type": "http",
            "path": "/api/v1/ar/summary",
            "headers": [],
            "state": {},
        }
        receive = MagicMock()
        send = AsyncMock()
        await middleware(scope, receive, send)
        send.assert_called()
        # Starlette RedirectResponse calls send twice: start + body
        first_call = send.call_args_list[0]
        assert first_call[0][0]["type"] == "http.response.start"
        assert first_call[0][0]["status"] == 302

    async def test_public_path_without_session_allowed(self, middleware):
        """Public paths are served even without a session."""
        scope = {
            "type": "http",
            "path": "/health",
            "headers": [],
            "state": {},
        }
        receive = MagicMock()
        send = AsyncMock()
        # Replace app with an async callable that records calls
        app = AsyncMock()
        middleware.app = app
        await middleware(scope, receive, send)
        app.assert_called_once_with(scope, receive, send)

    async def test_invalid_session_treated_as_no_session(self, middleware):
        """Invalid session cookie is treated as no session."""
        scope = {
            "type": "http",
            "path": "/api/v1/ar/summary",
            "headers": [(b"cookie", b"finboss_session=invalid_session_id")],
            "state": {},
        }
        receive = MagicMock()
        send = AsyncMock()
        await middleware(scope, receive, send)
        send.assert_called()
        first_call = send.call_args_list[0]
        assert first_call[0][0]["type"] == "http.response.start"
        assert first_call[0][0]["status"] == 302

    async def test_non_http_scope_passes_through(self, middleware):
        """WebSocket and other non-HTTP scopes pass through unchanged."""
        scope = {
            "type": "websocket",
            "path": "/ws",
            "headers": [],
            "state": {},
        }
        receive = MagicMock()
        send = AsyncMock()
        app = AsyncMock()
        middleware.app = app
        await middleware(scope, receive, send)
        app.assert_called_once_with(scope, receive, send)
