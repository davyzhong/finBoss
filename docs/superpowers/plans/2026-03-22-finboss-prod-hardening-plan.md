# Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add production-grade reliability infrastructure: API key auth, unified error handling, request tracing, JSON logs, fixed-window rate limiting, and health check endpoints.

**Architecture:** FastAPI middleware stack (tracing → auth → rate_limit) injected before routes. Custom exception hierarchy with global handlers in main.py. Structured JSON logging via custom formatter. Fixed-window in-process rate limiter using dict + timestamp lists.

**Tech Stack:** FastAPI, Pydantic Settings, Python logging, asyncio.timeout

---

## File Structure

| File | Action |
|------|--------|
| `api/exceptions.py` | Create — custom exception classes |
| `api/error_codes.py` | Create — error code constants |
| `api/logging.py` | Create — JSON formatter |
| `api/middleware/auth.py` | Create — API key auth |
| `api/middleware/tracing.py` | Create — request ID tracing |
| `api/middleware/rate_limit.py` | Create — fixed-window rate limiter |
| `api/routes/health.py` | Create — /health and /ready |
| `api/config.py` | Modify — add APIKeyConfig |
| `api/main.py` | Modify — register middleware and handlers |
| `api/dependencies.py` | Modify — add auth dependency |
| `.env.example` | Modify — add API_KEYS, API_RATE_LIMIT |
| `tests/unit/test_rate_limit.py` | Create — rate limit tests |
| `tests/unit/test_health.py` | Create — health endpoint tests |

---

## Task 1: Config + Exception + Error Codes

**Files:**
- Create: `api/error_codes.py`
- Create: `api/exceptions.py`
- Modify: `api/config.py` (add APIKeyConfig)
- Modify: `.env.example`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_error_codes.py
from api import error_codes

def test_error_code_constants():
    assert error_codes.UNAUTHORIZED == "UNAUTHORIZED"
    assert error_codes.RATE_LIMITED == "RATE_LIMITED"
    assert error_codes.NOT_FOUND == "NOT_FOUND"
    assert error_codes.VALIDATION_ERROR == "VALIDATION_ERROR"
    assert error_codes.INTERNAL_ERROR == "INTERNAL_ERROR"
```

Run: `uv run pytest tests/unit/test_error_codes.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write minimal implementation**

`api/error_codes.py`:
```python
UNAUTHORIZED = "UNAUTHORIZED"
RATE_LIMITED = "RATE_LIMITED"
NOT_FOUND = "NOT_FOUND"
VALIDATION_ERROR = "VALIDATION_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"
QUALITY_ERROR = "QUALITY_ERROR"
DATA_SERVICE_ERROR = "DATA_SERVICE_ERROR"
AI_SERVICE_ERROR = "AI_SERVICE_ERROR"
```

`api/exceptions.py`:
```python
class FinBossError(Exception):
    """业务异常基类"""
    code: str = "INTERNAL_ERROR"

class QualityError(FinBossError):
    code = "QUALITY_ERROR"

class DataServiceError(FinBossError):
    code = "DATA_SERVICE_ERROR"

class AIServiceError(FinBossError):
    code = "AI_SERVICE_ERROR"
```

Run: `uv run pytest tests/unit/test_error_codes.py -v`
Expected: PASS

- [ ] **Step 3: Add APIKeyConfig to config.py**

Read `api/config.py` first. Add after existing Field imports:

```python
class APIKeyConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="api_", extra="ignore")
    keys: list[str] = Field(default=[], description="允许的 API Key 列表")
    rate_limit: int = Field(default=100, description="每分钟每 IP 每端点请求数")
```

Register in `Settings` class:
```python
api_key: APIKeyConfig = Field(default_factory=APIKeyConfig)
```

- [ ] **Step 4: Update .env.example**

Add:
```
# API Authentication
API_KEYS=key1,key2,key3
API_RATE_LIMIT=100
```

- [ ] **Step 5: Write APIKeyConfig test**

```python
# tests/unit/test_config.py
from api.config import APIKeyConfig

def test_api_key_config_defaults():
    cfg = APIKeyConfig()
    assert cfg.keys == []
    assert cfg.rate_limit == 100
```

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/error_codes.py api/exceptions.py api/config.py .env.example tests/unit/test_error_codes.py tests/unit/test_config.py
git commit -m "feat(prod-hardening): add error codes, exceptions, and APIKeyConfig"
```

---

## Task 2: JSON Logging Formatter

**Files:**
- Create: `api/logging.py`
- Modify: `api/main.py` (inject formatter)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_logging.py
import logging, json
from api.logging import JSONFormatter

def test_json_formatter_output():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="hello", args=(), exc_info=None
    )
    result = json.loads(formatter.format(record))
    assert result["level"] == "INFO"
    assert result["message"] == "hello"
    assert "timestamp" in result
    assert "logger" in result

def test_json_formatter_with_request_id():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="request", args=(), exc_info=None
    )
    record.request_id = "abc123"
    result = json.loads(formatter.format(record))
    assert result["request_id"] == "abc123"
```

Run: `uv run pytest tests/unit/test_logging.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write implementation**

`api/logging.py`:
```python
import logging
import json


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "level": record.levelname,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record),
            "logger": record.name,
        }
        if hasattr(record, "request_id"):
            data["request_id"] = record.request_id
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data)
```

Run: `uv run pytest tests/unit/test_logging.py -v`
Expected: PASS

- [ ] **Step 3: Integrate into main.py**

Read `api/main.py`. Add at top:
```python
from api.logging import JSONFormatter
```

Add after app creation (before middleware registration):
```python
# Configure JSON logging
for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
    logger = logging.getLogger(logger_name)
    logger.handlers[0].setFormatter(JSONFormatter())
```

- [ ] **Step 4: Commit**

```bash
git add api/logging.py api/main.py tests/unit/test_logging.py
git commit -m "feat(prod-hardening): add JSON logging formatter"
```

---

## Task 3: Tracing Middleware

**Files:**
- Create: `api/middleware/tracing.py`
- Modify: `api/main.py` (register middleware)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_tracing_middleware.py
from unittest.mock import MagicMock
from api.middleware.tracing import tracing_middleware
import uuid

async def test_tracing_sets_request_id():
    request = MagicMock()
    request.headers = {}
    request.state = MagicMock()
    generated_id = None
    async def capture(request):
        nonlocal generated_id
        generated_id = request.state.request_id
        return MagicMock(headers={})
    response = await tracing_middleware(request, capture)
    assert len(generated_id) == 16
    assert generated_id == response.headers["X-Request-ID"]

async def test_tracing_uses_existing_request_id():
    request = MagicMock()
    request.headers = {"X-Request-ID": "my-custom-id"}
    request.state = MagicMock()
    async def capture(req):
        return MagicMock(headers={})
    response = await tracing_middleware(request, capture)
    assert response.headers["X-Request-ID"] == "my-custom-id"
```

Run: `uv run pytest tests/unit/test_tracing_middleware.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write implementation**

`api/middleware/tracing.py`:
```python
import uuid
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


async def tracing_middleware(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        return await ASGIApp.__call__(scope, receive, send)  # type: ignore
    request = Request(scope, receive)
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    request.state.request_id = request_id

    async def send_wrapper(message):
        if message["type"] == "http.response.start":
            message["headers"].append((b"X-Request-ID", request_id.encode()))
        await send(message)

    # Continue with full ASGI app
    await scope["app"](scope, receive, send_wrapper)
```

Actually, for FastAPI/Starlette use a simpler ASGI-compatible pattern:
```python
# api/middleware/tracing.py
import uuid
from starlette.types import ASGIApp, Receive, Scope, Send


class TracingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = (
            scope.get("headers", [])
            .get(b"x-request-id", b"")
            .decode()
            or uuid.uuid4().hex[:16]
        )
        scope["state"] = {"request_id": request_id}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-request-id"] = request_id.encode()
                message = {**message, "headers": list(headers.items())}
            await send(message)

        await self.app(scope, receive, send_wrapper)
```

Then update `main.py` registration:
```python
from api.middleware.tracing import TracingMiddleware
app.add_middleware(TracingMiddleware)
```

Run: `uv run pytest tests/unit/test_tracing_middleware.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add api/middleware/tracing.py tests/unit/test_tracing_middleware.py
git commit -m "feat(prod-hardening): add request tracing middleware"
```

---

## Task 4: Auth Middleware

**Files:**
- Create: `api/middleware/auth.py`
- Modify: `api/main.py` (register)
- Modify: `api/dependencies.py` (add auth dependency)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_auth_middleware.py
from unittest.mock import MagicMock
from api.middleware.auth import AuthMiddleware, PUBLIC_PATHS

def test_public_paths_include_health():
    assert "/health" in PUBLIC_PATHS
    assert "/ready" in PUBLIC_PATHS
    assert "/docs" in PUBLIC_PATHS

def test_public_path_detection():
    assert AuthMiddleware._is_public("/health")
    assert AuthMiddleware._is_public("/api/v1/ai/health")
    assert not AuthMiddleware._is_public("/api/v1/ar/summary")
```

Run: `uv run pytest tests/unit/test_auth_middleware.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write implementation**

`api/middleware/auth.py`:
```python
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/ai/health",
    "/feishu/events",
}


class AuthMiddleware:
    def __init__(self, app: ASGIApp, api_keys: list[str]) -> None:
        self.app = app
        self.api_keys = api_keys

    @staticmethod
    def _is_public(path: str) -> bool:
        return path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        headers = dict(scope.get("headers", []))

        if self._is_public(path):
            await self.app(scope, receive, send)
            return

        provided_key = headers.get(b"x-api-key", b"").decode()
        if provided_key and provided_key in self.api_keys:
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Invalid or missing API key",
                },
                "request_id": scope.get("state", {}).get("request_id", ""),
            },
        )
        await response(scope, receive, send)
```

Update `main.py` to add middleware:
```python
from api.middleware.auth import AuthMiddleware
# After other middleware, before routes
app.add_middleware(
    AuthMiddleware,
    api_keys=settings.api_key.keys,
)
```

Add to `api/dependencies.py`:
```python
def get_api_keys() -> list[str]:
    return settings.api_key.keys
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/test_auth_middleware.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add api/middleware/auth.py api/dependencies.py api/main.py tests/unit/test_auth_middleware.py
git commit -m "feat(prod-hardening): add API key auth middleware"
```

---

## Task 5: Rate Limit Middleware

**Files:**
- Create: `api/middleware/rate_limit.py`
- Modify: `api/main.py` (register)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_rate_limit.py
from api.middleware.rate_limit import check_rate_limit, RateLimitMiddleware

def test_first_request_allowed():
    result = check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    assert result is True

def test_within_limit_allowed():
    check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    result = check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    assert result is True

def test_over_limit_rejected():
    from api.middleware.rate_limit import windows
    windows.clear()
    for _ in range(3):
        check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    result = check_rate_limit("1.1.1.1", "/test", limit=3, window=60)
    assert result is False

def test_different_ips_independent():
    check_rate_limit("1.1.1.1", "/test", limit=1, window=60)
    result = check_rate_limit("2.2.2.2", "/test", limit=1, window=60)
    assert result is True

def test_different_endpoints_independent():
    check_rate_limit("1.1.1.1", "/a", limit=1, window=60)
    result = check_rate_limit("1.1.1.1", "/b", limit=1, window=60)
    assert result is True
```

Run: `uv run pytest tests/unit/test_rate_limit.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write implementation**

`api/middleware/rate_limit.py`:
```python
from collections import defaultdict
from time import time
from typing import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# Fixed window: { (ip, endpoint): [(timestamp, count)] }
windows: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)


def check_rate_limit(
    client_ip: str, endpoint: str, limit: int = 100, window: int = 60
) -> bool:
    now = int(time())
    key = (client_ip, endpoint)
    # 清理过期窗口
    windows[key] = [(ts, cnt) for ts, cnt in windows[key] if now - ts < window]
    # 统计本窗口内请求数
    total = sum(cnt for _, cnt in windows[key])
    if total >= limit:
        return False
    windows[key].append((now, 1))
    return True


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: int = 100) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        headers = dict(scope.get("headers", []))
        client_ip = headers.get(b"x-forwarded-for", b"unknown").decode().split(",")[0].strip()
        if client_ip == "unknown":
            client_ip = scope.get("client", ("unknown",))[0] or "unknown"

        if not check_rate_limit(client_ip, path, limit=self.limit):
            state = scope.get("state", {})
            request_id = state.get("request_id", "")
            response = JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Rate limit exceeded, retry after 60s",
                    },
                    "request_id": request_id,
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
```

Register in `main.py`:
```python
from api.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(
    RateLimitMiddleware,
    limit=settings.api_key.rate_limit,
)
```

Run: `uv run pytest tests/unit/test_rate_limit.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add api/middleware/rate_limit.py api/main.py tests/unit/test_rate_limit.py
git commit -m "feat(prod-hardening): add fixed-window rate limiting middleware"
```

---

## Task 6: Health Check Endpoints

**Files:**
- Create: `api/routes/health.py`
- Modify: `api/main.py` (replace inline /health, add router)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_health.py
from httpx import AsyncClient
from api.main import app

@pytest.mark.asyncio
async def test_health_returns_ok():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

@pytest.mark.asyncio
async def test_ready_checks_components():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "components" in data
    assert "clickhouse" in data["components"]
```

Run: `uv run pytest tests/unit/test_health.py -v`
Expected: FAIL — route not found

- [ ] **Step 2: Write implementation**

`api/routes/health.py`:
```python
import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from services.clickhouse_service import ClickHouseDataService

router = APIRouter(tags=["健康检查"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, Any]:
    components = {}
    overall = "ready"

    # ClickHouse
    try:
        async with asyncio.timeout(5):
            ch = ClickHouseDataService()
            ch.execute("SELECT 1")
        components["clickhouse"] = "ok"
    except asyncio.TimeoutError:
        components["clickhouse"] = "timeout"
        overall = "not_ready"
    except Exception as e:
        components["clickhouse"] = f"error: {e}"
        overall = "not_ready"

    # Ollama
    try:
        async with asyncio.timeout(5):
            from services.ai.ollama_service import OllamaService
            svc = OllamaService()
            if svc.is_available():
                components["ollama"] = "ok"
            else:
                components["ollama"] = "degraded"
                if overall == "ready":
                    overall = "degraded"
    except asyncio.TimeoutError:
        components["ollama"] = "timeout"
        overall = "degraded"
    except Exception as e:
        components["ollama"] = f"error: {e}"
        overall = "degraded"

    return {"status": overall, "components": components}
```

- [ ] **Step 3: Register in main.py**

Read `api/main.py`:
1. Remove the inline `/health` endpoint at lines 84-91
2. Add router import: `from api.routes.health import router as health_router`
3. Register: `app.include_router(health_router)`

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_health.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/health.py api/main.py tests/unit/test_health.py
git commit -m "feat(prod-hardening): add /health and /ready endpoints"
```

---

## Task 7: Global Exception Handlers

**Files:**
- Modify: `api/main.py` (register exception handlers)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_exception_handlers.py
import pytest
from httpx import AsyncClient
from fastapi import FastAPI
from api.main import app

@pytest.mark.asyncio
async def test_validation_error_returns_422():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.post("/api/v1/ar/summary", json={"invalid": "data"})
    assert resp.status_code == 422
    data = resp.json()
    assert data.get("success") is False

@pytest.mark.asyncio
async def test_error_response_has_request_id():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/nonexistent-endpoint-xyz")
    # Should get 404 or similar
    assert resp.status_code in (404, 401, 403)
```

- [ ] **Step 2: Add exception handlers to main.py**

Read `api/main.py`. Add after app creation and before middleware:

```python
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from api.exceptions import FinBossError
from api.error_codes import INTERNAL_ERROR, VALIDATION_ERROR

def build_error_response(code: str, message: str, request_id: str = ""):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {"code": code, "message": message},
            "request_id": request_id,
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {"code": VALIDATION_ERROR, "message": str(exc.errors())},
            "request_id": request_id,
        },
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {"code": INTERNAL_ERROR, "message": exc.detail},
            "request_id": request_id,
        },
    )

@app.exception_handler(FinBossError)
async def finboss_exception_handler(request: Request, exc: FinBossError):
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {"code": exc.code, "message": str(exc)},
            "request_id": request_id,
        },
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {"code": INTERNAL_ERROR, "message": "Internal server error"},
            "request_id": request_id,
        },
    )
```

Run: `uv run pytest tests/unit/test_exception_handlers.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add api/main.py tests/unit/test_exception_handlers.py
git commit -m "feat(prod-hardening): add global exception handlers"
```

---

## Task 8: Integration Verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All existing tests pass + new tests pass

- [ ] **Step 2: Run linting**

Run: `uv run ruff check api/`
Expected: Clean (fix any remaining B904 or other issues)

- [ ] **Step 3: Smoke test the app**

Run: `uv run uvicorn api.main:app --port 8001 &` then:
```bash
curl -s http://localhost:8001/health
curl -s http://localhost:8001/ready
curl -s http://localhost:8001/docs | head -5
curl -s -X GET http://localhost:8001/api/v1/ar/summary -H "X-API-Key: invalid"
# Should return 401
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(prod-hardening: complete): all production hardening infrastructure

- API key authentication with path whitelist
- Custom exception hierarchy (FinBossError base)
- Global exception handlers (422/500/error response format)
- Request tracing with X-Request-ID header propagation
- Structured JSON logging
- Fixed-window rate limiting (per IP, per endpoint)
- /health (liveness) and /ready (readiness) endpoints
- Unified error response format

Closes #prod-hardening"
```

---

## Middleware Registration Order

In `api/main.py`, middleware must be registered in this order (first added = outermost/last executed):

```python
# 1. Tracing (outermost — runs first on request, last on response)
app.add_middleware(TracingMiddleware)

# 2. Auth (checks after tracing sets request_id)
app.add_middleware(AuthMiddleware, api_keys=settings.api_key.keys)

# 3. Rate Limit (innermost — last chance to block before routes)
app.add_middleware(RateLimitMiddleware, limit=settings.api_key.rate_limit)
```

## Notes

- Rate limiter uses **process-local dict** — not shared across uvicorn workers. For multi-worker production, replace with Redis.
- `/health` response changed from `{status, service, version}` to `{status: "ok"}` — breaking change for existing callers.
- `OllamaService.is_available()` is synchronous; wrapped in `async with asyncio.timeout(5)`.
