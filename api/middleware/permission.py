from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


# 角色 × 模块权限矩阵（只读/读写）
ROLE_PERMISSIONS = {
    "finance": {
        "ar": {"read": True, "write": False},
        "ap": {"read": True, "write": False},
        "reports": {"read": True, "write": False},
        "alerts": {"read": True, "write": False},
        "quality": {"read": True, "write": False},
        "admin": {"read": False, "write": False},
    },
    "sales_manager": {
        "ar": {"read": True, "write": False},
        "ap": {"read": False, "write": False},
        "reports": {"read": True, "write": False},
        "alerts": {"read": True, "write": False},
        "quality": {"read": False, "write": False},
        "admin": {"read": False, "write": False},
    },
    "ops": {
        "ar": {"read": False, "write": False},
        "ap": {"read": False, "write": False},
        "reports": {"read": True, "write": False},
        "alerts": {"read": True, "write": True},
        "quality": {"read": True, "write": True},
        "admin": {"read": False, "write": False},
    },
    "admin": {
        "ar": {"read": True, "write": True},
        "ap": {"read": True, "write": True},
        "reports": {"read": True, "write": True},
        "alerts": {"read": True, "write": True},
        "quality": {"read": True, "write": True},
        "admin": {"read": True, "write": True},
    },
}


def path_to_module(path: str) -> str | None:
    """从请求路径提取模块名"""
    if path.startswith("/api/v1/ar"):
        return "ar"
    if path.startswith("/api/v1/ap"):
        return "ap"
    if path.startswith("/api/v1/reports"):
        return "reports"
    if path.startswith("/api/v1/alerts"):
        return "alerts"
    if path.startswith("/api/v1/quality"):
        return "quality"
    if path.startswith("/api/v1/admin"):
        return "admin"
    return None


def check_permission(role: str, module: str, method: str) -> bool:
    """检查角色对模块的指定操作是否有权限"""
    perms = ROLE_PERMISSIONS.get(role, {}).get(module)
    if perms is None:
        return False
    if method in ("GET", "HEAD", "OPTIONS"):
        return perms.get("read", False)
    return perms.get("write", False)


class PermissionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        user = scope.get("state", {}).get("user")
        if not user:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")
        module = path_to_module(path)

        if module and not check_permission(user.get("role", ""), module, method):
            response = JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": {"code": "FORBIDDEN", "message": "无权访问此模块"},
                    "request_id": scope.get("state", {}).get("request_id", ""),
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
