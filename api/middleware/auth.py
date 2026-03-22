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
        # Exact match for known public paths
        if path in PUBLIC_PATHS:
            return True
        # Prefix match for docs/redoc/openapi
        for public in ("/docs", "/redoc", "/openapi"):
            if path.startswith(public):
                return True
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        headers_list = scope.get("headers", [])
        headers_dict = {k.decode().lower(): v.decode() for k, v in headers_list}

        if self._is_public(path):
            await self.app(scope, receive, send)
            return

        provided_key = headers_dict.get("x-api-key", "")
        if provided_key and provided_key in self.api_keys:
            await self.app(scope, receive, send)
            return

        # Unauthorized — return JSON error
        state = scope.get("state", {})
        request_id = state.get("request_id", "")
        response = JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Invalid or missing API key",
                },
                "request_id": request_id,
            },
            headers={"WWW-Authenticate": "X-API-Key"},
        )
        await response(scope, receive, send)
