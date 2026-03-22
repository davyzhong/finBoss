from collections import defaultdict
from time import time

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# Fixed window: { (ip, endpoint): [(timestamp, count)] }
windows: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)


def check_rate_limit(
    client_ip: str, endpoint: str, limit: int = 100, window: int = 60
) -> bool:
    """Check if a request should be rate limited. Returns True if allowed."""
    now = int(time())
    key = (client_ip, endpoint)
    # Clean up expired entries
    windows[key] = [(ts, cnt) for ts, cnt in windows[key] if now - ts < window]
    # Count requests in current window
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
        headers_list = scope.get("headers", [])
        headers_dict = {k.decode().lower(): v.decode() for k, v in headers_list}

        # Get client IP from X-Forwarded-For or direct client
        forwarded = headers_dict.get("x-forwarded-for", "")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
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
                        "message": "Rate limit exceeded, retry after 60s",
                    },
                    "request_id": request_id,
                },
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
