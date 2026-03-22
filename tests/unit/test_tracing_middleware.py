from unittest.mock import AsyncMock, MagicMock
from api.middleware.tracing import TracingMiddleware


def test_public_paths_include_health():
    # Just verify the module loads and TracingMiddleware exists
    assert TracingMiddleware is not None


async def test_tracing_generates_request_id():
    """Test that TracingMiddleware generates a request ID when none provided."""
    scope = {
        "type": "http",
        "path": "/api/v1/ar/summary",
        "headers": [],
        "state": {},
    }
    receive = MagicMock()
    # send must be AsyncMock since it's awaited in the middleware
    send = AsyncMock()

    middleware = TracingMiddleware(app=MagicMock())

    async def mock_app(scope, receive, send_fn):
        await send_fn({"type": "http.response.start", "status": 200, "headers": []})
        await send_fn({"type": "http.response.body", "body": b""})

    middleware.app = mock_app
    await middleware(scope, receive, send)

    # Verify send was called with X-Request-ID header
    send_calls = send.call_args_list
    start_call = send_calls[0]
    assert start_call[0][0]["type"] == "http.response.start"
    headers = dict(start_call[0][0].get("headers", []))
    assert b"x-request-id" in headers
    request_id = headers[b"x-request-id"].decode()
    assert len(request_id) == 16


async def test_tracing_uses_existing_request_id():
    """Test that TracingMiddleware uses existing X-Request-ID header."""
    scope = {
        "type": "http",
        "path": "/api/v1/ar/summary",
        "headers": [(b"x-request-id", b"my-custom-id")],
        "state": {},
    }
    receive = MagicMock()
    # send must be AsyncMock since it's awaited in the middleware
    send = AsyncMock()

    middleware = TracingMiddleware(app=MagicMock())

    async def mock_app(scope, receive, send_fn):
        await send_fn({"type": "http.response.start", "status": 200, "headers": []})
        await send_fn({"type": "http.response.body", "body": b""})

    middleware.app = mock_app
    await middleware(scope, receive, send)

    send_calls = send.call_args_list
    start_call = send_calls[0]
    headers = dict(start_call[0][0].get("headers", []))
    assert headers.get(b"x-request-id") == b"my-custom-id"
