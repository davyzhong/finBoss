import uuid
from starlette.types import ASGIApp, Receive, Scope, Send


class TracingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract or generate request ID
        headers_list = scope.get("headers", [])
        headers_dict = {k.decode().lower(): v.decode() for k, v in headers_list}
        request_id = headers_dict.get("x-request-id") or uuid.uuid4().hex[:16]

        # Store in scope state for downstream access
        scope["state"]["request_id"] = request_id

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-request-id"] = request_id.encode()
                message = {**message, "headers": list(headers.items())}
            await send(message)

        await self.app(scope, receive, send_wrapper)
