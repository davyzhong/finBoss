from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = frozenset({
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/login",
    "/auth/callback",
    "/api/v1/ai/health",
    "/feishu/events",
})


def requires_auth(path: str) -> bool:
    """Return True if the path requires authentication (not in the public whitelist)."""
    return not any(
        path == p or path.startswith(p + "/") for p in PUBLIC_PATHS
    )


def parse_cookies(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    """Parse Cookie header bytes into a {name: value} dictionary."""
    result = {}
    for k, v in headers:
        if k.lower() == b"cookie":
            for part in v.decode().split(";"):
                part = part.strip()
                if "=" in part:
                    name, val = part.split("=", 1)
                    result[name.strip()] = val.strip()
    return result


class SessionMiddleware:
    def __init__(self, app: ASGIApp, session_store=None) -> None:
        from services.session_service import InMemorySessionStore

        self.app = app
        self.session_store = session_store or InMemorySessionStore()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cookies = parse_cookies(scope.get("headers", []))
        session_id = cookies.get("finboss_session", "")

        if session_id:
            user = self.session_store.get(session_id)
            if user:
                scope["state"]["user"] = user
            else:
                session_id = ""

        path = scope.get("path", "")
        if not session_id and requires_auth(path):
            from starlette.responses import RedirectResponse

            response = RedirectResponse(url="/auth/login", status_code=302)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
