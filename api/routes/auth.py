import secrets
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from api.config import get_settings
from services.auth_provider.dingtalk_oauth import DingTalkOAuthProvider
from services.auth_provider.feishu_oauth import FeishuOAuthProvider
from services.auth_provider.wecom_oauth import WeComOAuthProvider
from services.clickhouse_service import ClickHouseDataService
from services.session_service import InMemorySessionStore
from services.session_service import session_store as _global_session_store

router = APIRouter(tags=["认证"])

_PROVIDERS = {
    "feishu": FeishuOAuthProvider,
    "dingtalk": DingTalkOAuthProvider,
    "wecom": WeComOAuthProvider,
}

_csrf_store: dict[str, str] = {}  # state -> provider


def _get_or_create_user(provider: str, external_id: str, name: str, email: str) -> dict:
    """查找或创建本地用户，默认角色为 finance"""
    ch = ClickHouseDataService()
    # Parameterized query to prevent SQL injection
    result = ch.client.execute(
        "SELECT user_id, role, is_active FROM dm.users WHERE external_id = %(eid)s AND provider = %(prov)s",
        {"eid": external_id, "prov": provider},
    )
    if result:
        row = result[0]
        return {"user_id": row[0], "role": row[1], "is_active": bool(row[2])}
    user_id = str(uuid.uuid4())
    default_role = "finance"
    now = datetime.utcnow()
    ch.client.execute(
        "INSERT INTO dm.users (user_id, external_id, provider, name, email, role, created_at, updated_at) "
        "VALUES",
        {
            "user_id": user_id,
            "external_id": external_id,
            "provider": provider,
            "name": name,
            "email": email,
            "role": default_role,
            "created_at": now,
            "updated_at": now,
        },
    )
    return {"user_id": user_id, "role": default_role, "is_active": True}


@router.get("/login")
async def login(provider: str | None = None) -> Response:
    """显示提供商选择页，或重定向到指定 IdP"""
    if provider is None:
        html = """
        <html><body>
        <h2>选择登录方式</h2>
        <ul>
          <li><a href="/auth/login?provider=feishu">飞书</a></li>
          <li><a href="/auth/login?provider=dingtalk">钉钉</a></li>
          <li><a href="/auth/login?provider=wecom">企业微信</a></li>
        </ul>
        </body></html>
        """
        return HTMLResponse(html)
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=400, detail="不支持的登录方式")
    state = secrets.token_urlsafe(16)
    _csrf_store[state] = provider
    oauth_provider = _PROVIDERS[provider]()
    auth_url, _ = oauth_provider.get_authorization_url(state)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
async def callback(
    code: str | None = Query(default=None),
    state: str = Query(default=""),
    provider: str = Query(default=""),
):
    # Handle missing code gracefully -> 400
    if not code:
        raise HTTPException(status_code=400, detail="缺少 code 参数")

    # CSRF validation
    stored_provider = _csrf_store.pop(state, None)
    if not stored_provider:
        raise HTTPException(status_code=400, detail="无效的 state，请重新登录")

    oauth_provider = _PROVIDERS[stored_provider]()

    # Exchange code for token + user info
    raw_data = oauth_provider.exchange_code(code)
    user_info = oauth_provider._parse_user_info(raw_data, raw_data)

    # Lookup or create local user
    local_user = _get_or_create_user(
        provider=stored_provider,
        external_id=user_info["external_id"],
        name=user_info["name"],
        email=user_info["email"],
    )

    if not local_user.get("is_active", True):
        raise HTTPException(status_code=403, detail="账户已被禁用")

    # Create session
    session_store = InMemorySessionStore()
    session_id = session_store.create({
        "user_id": local_user["user_id"],
        "external_id": user_info["external_id"],
        "provider": stored_provider,
        "name": user_info["name"],
        "email": user_info["email"],
        "role": local_user["role"],
        "is_active": True,
    })

    # Redirect to home
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="finboss_session",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=8 * 3600,
        secure=not get_settings().app.debug,
    )
    return response


@router.delete("/logout")
async def logout(request: Request, response: Response):
    """登出：删除 session，清除 cookie"""
    session_id = request.cookies.get("finboss_session", "")
    if session_id:
        _global_session_store.pop(session_id, None)
    resp = Response(status_code=200)
    resp.delete_cookie("finboss_session")
    return {"success": True}


@router.get("/me")
async def me(request: Request) -> dict[str, Any]:
    """返回当前用户信息"""
    user = getattr(request.state, "user", None) if hasattr(request, "state") else None
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return {
        "user_id": user.get("user_id", ""),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "role": user.get("role", ""),
        "provider": user.get("provider", ""),
    }
