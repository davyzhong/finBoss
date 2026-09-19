# Phase 8 SSO + RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-IdP OAuth 2.0 SSO login + standard RBAC session-based authentication for FinBoss.

**Architecture:** In-memory session store keyed by secure random token; per-provider OAuth client modules; ASGI middleware stack for session parsing and permission enforcement; ClickHouse RBAC tables for roles × permissions.

**Tech Stack:** Python `secrets`, Starlette/FastAPI middleware, ClickHouse ReplacingMergeTree, OAuth 2.0 (飞书/钉钉/企微)

---

## Task 1: Config + Session Store + Schemas

**Files:**
- Create: `schemas/user.py`
- Modify: `api/config.py`
- Create: `services/session_service.py`
- Create: `tests/unit/test_session_service.py`
- Create: `tests/unit/test_schemas.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_session_service.py
import pytest, time
from services.session_service import SessionStore, InMemorySessionStore

def test_create_returns_session_id():
    store = InMemorySessionStore()
    sid = store.create({"user_id": "u1", "role": "admin"})
    assert isinstance(sid, str)
    assert len(sid) > 20

def test_get_returns_user_info():
    store = InMemorySessionStore()
    sid = store.create({"user_id": "u1", "role": "admin", "name": "张三"})
    result = store.get(sid)
    assert result["user_id"] == "u1"
    assert result["role"] == "admin"
    assert result["name"] == "张三"

def test_get_expired_returns_none():
    store = InMemorySessionStore()
    sid = store.create({"user_id": "u1"}, ttl_hours=0)  # expires immediately
    time.sleep(0.1)
    assert store.get(sid) is None

def test_delete_removes_session():
    store = InMemorySessionStore()
    sid = store.create({"user_id": "u1"})
    store.delete(sid)
    assert store.get(sid) is None

def test_get_unknown_returns_none():
    store = InMemorySessionStore()
    assert store.get("unknown-id") is None
```

```python
# tests/unit/test_schemas.py
from schemas.user import User, Role, RolePermission

def test_user_schema():
    u = User(user_id="u1", external_id="ext1", provider="feishu",
              name="张三", email="z@test.com", role="admin")
    assert u.user_id == "u1"
    assert u.is_active is True

def test_role_schema():
    r = Role(role_id="admin", role_name="管理员", desc="系统管理员")
    assert r.role_id == "admin"

def test_role_permission_schema():
    rp = RolePermission(role_id="admin", module="ar", can_read=True, can_write=True)
    assert rp.can_read is True
    assert rp.can_write is True
```

Run: `uv run pytest tests/unit/test_session_service.py tests/unit/test_schemas.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write schemas/user.py**

```python
from datetime import datetime
from pydantic import BaseModel, Field


class User(BaseModel):
    user_id: str = Field(description="本地用户ID（UUID）")
    external_id: str = Field(description="IdP 的 union_id / user_id")
    provider: str = Field(description="feishu | dingtalk | wecom")
    name: str = Field(default="")
    email: str = Field(default="")
    role: str = Field(default="")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Role(BaseModel):
    role_id: str = Field(description="角色ID")
    role_name: str = Field(description="角色名")
    desc: str = Field(default="", description="描述")


class RolePermission(BaseModel):
    role_id: str = Field(description="角色ID")
    module: str = Field(description="模块名（ar/ap/reports/alerts/quality/admin）")
    can_read: bool = Field(default=False)
    can_write: bool = Field(default=False)
```

- [ ] **Step 3: Write services/session_service.py**

```python
from datetime import datetime, timedelta
from secrets import token_urlsafe
from typing import Optional


session_store: dict[str, dict] = {}


class InMemorySessionStore:
    """内存 Session 存储（开发用，生产换 Redis）"""

    def create(self, user_info: dict, ttl_hours: int = 8) -> str:
        session_id = token_urlsafe(32)
        session_store[session_id] = {
            **user_info,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=ttl_hours),
        }
        return session_id

    def get(self, session_id: str) -> Optional[dict]:
        session = session_store.get(session_id)
        if session and session["expires_at"] > datetime.utcnow():
            return session
        session_store.pop(session_id, None)
        return None

    def delete(self, session_id: str) -> None:
        session_store.pop(session_id, None)
```

- [ ] **Step 4: Add OAuth configs to api/config.py**

Read `api/config.py`. Add these classes BEFORE the `Settings` class:

```python
class FeishuOAuthConfig(BaseSettings):
    """飞书 OAuth 配置"""

    model_config = SettingsConfigDict(
        env_prefix="feishu_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_id: str = Field(default="", description="飞书应用 App ID")
    app_secret: str = Field(default="", description="飞书应用 App Secret")
    redirect_uri: str = Field(default="", description="OAuth 回调地址")
    scope: str = Field(
        default="contact:user.avatar:readonly contact:user.email:readonly",
        description="权限范围",
    )


class DingTalkOAuthConfig(BaseSettings):
    """钉钉 OAuth 配置"""

    model_config = SettingsConfigDict(
        env_prefix="dingtalk_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_id: str = Field(default="", description="钉钉应用 AppKey")
    app_secret: str = Field(default="", description="钉钉应用 AppSecret")
    redirect_uri: str = Field(default="", description="OAuth 回调地址")


class WeComOAuthConfig(BaseSettings):
    """企业微信 OAuth 配置"""

    model_config = SettingsConfigDict(
        env_prefix="wecom_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    corp_id: str = Field(default="", description="企业 ID")
    corp_secret: str = Field(default="", description="企业微信应用 Secret")
    agent_id: str = Field(default="", description="应用 AgentID")
    redirect_uri: str = Field(default="", description="OAuth 回调地址")
```

Add to `Settings` class (after `ai_analysis: AIAnalysisConfig`):
```python
feishu_oauth: FeishuOAuthConfig = Field(default_factory=FeishuOAuthConfig)
dingtalk_oauth: DingTalkOAuthConfig = Field(default_factory=DingTalkOAuthConfig)
wecom_oauth: WeComOAuthConfig = Field(default_factory=WeComOAuthConfig)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_session_service.py tests/unit/test_schemas.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add schemas/user.py services/session_service.py api/config.py tests/unit/test_session_service.py tests/unit/test_schemas.py
git commit -m "feat(8): add OAuth configs, session store, and user schemas"
```

---

## Task 2: Feishu OAuth Provider

**Files:**
- Create: `services/auth_provider/feishu_oauth.py`
- Create: `tests/unit/test_feishu_oauth.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_feishu_oauth.py
from unittest.mock import patch, MagicMock
from services.auth_provider.feishu_oauth import FeishuOAuthProvider

def test_get_authorization_url_returns_redirect_url():
    with patch("services.auth_provider.feishu_oauth.get_settings") as mock_settings:
        mock_settings.return_value.feishu_oauth.app_id = "cli_test"
        mock_settings.return_value.feishu_oauth.redirect_uri = "http://test/callback"
        mock_settings.return_value.feishu_oauth.scope = "contact:user.email:readonly"
        provider = FeishuOAuthProvider()
        url, state = provider.get_authorization_url()
        assert url.startswith("https://open.feishu.cn/open-apis/authen/v1/authorize")
        assert "client_id=cli_test" in url
        assert len(state) > 10

def test_get_user_info_parses_response():
    provider = FeishuOAuthProvider()
    token_data = {"access_token": "test_token", "expires_in": 7200}
    user_data = {
        "data": {
            "user_id": "ou_test",
            "name": "张三",
            "email": "zhangsan@test.com",
        }
    }
    result = provider._parse_user_info(token_data, user_data)
    assert result["external_id"] == "ou_test"
    assert result["name"] == "张三"
    assert result["email"] == "zhangsan@test.com"
    assert result["provider"] == "feishu"
```

Run: `uv run pytest tests/unit/test_feishu_oauth.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write implementation**

Create `services/auth_provider/__init__.py`:
```python
```

Create `services/auth_provider/base.py`:
```python
from abc import ABC, abstractmethod
from typing import TypedDict


class OAuthUserInfo(TypedDict):
    external_id: str
    provider: str
    name: str
    email: str


class OAuthProvider(ABC):
    @abstractmethod
    def get_authorization_url(self, state: str) -> tuple[str, str]:
        """返回 (authorization_url, state)"""
        ...

    @abstractmethod
    def exchange_code(self, code: str) -> dict:
        """用 code 换取 access_token"""
        ...

    @abstractmethod
    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """用 access_token 获取用户信息"""
        ...
```

Create `services/auth_provider/feishu_oauth.py`:
```python
import httpx
from api.config import get_settings
from .base import OAuthProvider, OAuthUserInfo


class FeishuOAuthProvider(OAuthProvider):
    AUTHORIZE_URL = "https://open.feishu.cn/open-apis/authen/v1/authorize"
    TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token"
    USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"

    def get_authorization_url(self, state: str = "") -> tuple[str, str]:
        cfg = get_settings().feishu_oauth
        params = {
            "app_id": cfg.app_id,
            "redirect_uri": cfg.redirect_uri,
            "scope": cfg.scope,
            "state": state,
        }
        import urllib.parse
        query = urllib.parse.urlencode(params)
        url = f"{self.AUTHORIZE_URL}?{query}"
        return url, state

    def exchange_code(self, code: str) -> dict:
        cfg = get_settings().feishu_oauth
        import base64, httpx
        credentials = base64.b64encode(f"{cfg.app_id}:{cfg.app_secret}".encode()).decode()
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                self.TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/json",
                },
                json={"grant_type": "authorization_code", "code": code},
            )
            resp.raise_for_status()
            return resp.json()

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                self.USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_user_info({"access_token": access_token}, data)

    def _parse_user_info(self, token_data: dict, user_data: dict) -> OAuthUserInfo:
        d = user_data.get("data", {})
        return OAuthUserInfo(
            external_id=d.get("user_id", ""),
            provider="feishu",
            name=d.get("name", ""),
            email=d.get("email", ""),
        )
```

Run: `uv run pytest tests/unit/test_feishu_oauth.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add services/auth_provider/__init__.py services/auth_provider/base.py services/auth_provider/feishu_oauth.py tests/unit/test_feishu_oauth.py
git commit -m "feat(8): add Feishu OAuth provider"
```

---

## Task 3: DingTalk + WeCom OAuth Providers

**Files:**
- Create: `services/auth_provider/dingtalk_oauth.py`
- Create: `services/auth_provider/wecom_oauth.py`
- Create: `tests/unit/test_dingtalk_oauth.py`
- Create: `tests/unit/test_wecom_oauth.py`

- [ ] **Step 1: Write failing tests (parallel for both)**

```python
# tests/unit/test_dingtalk_oauth.py
from unittest.mock import patch
from services.auth_provider.dingtalk_oauth import DingTalkOAuthProvider

def test_get_authorization_url():
    with patch("services.auth_provider.dingtalk_oauth.get_settings") as mock:
        mock.return_value.dingtalk_oauth.app_id = "ding_app"
        mock.return_value.dingtalk_oauth.redirect_uri = "http://test/callback"
        provider = DingTalkOAuthProvider()
        url, state = provider.get_authorization_url("mystate")
        assert "oapi.dingtalk.com/connect/qrconnect" in url
        assert "appid=ding_app" in url
        assert "state=mystate" in url

def test_exchange_code_returns_token():
    with patch("services.auth_provider.dingtalk_oauth.get_settings") as mock:
        mock.return_value.dingtalk_oauth.app_id = "ding_app"
        mock.return_value.dingtalk_oauth.app_secret = "ding_secret"
        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.post.return_value.json.return_value = {"access_token": "tok", "errmsg": "ok"}
            mock_instance.post.return_value.raise_for_status = MagicMock()
            mock_client.return_value = mock_instance
            provider = DingTalkOAuthProvider()
            result = provider.exchange_code("test_code")
            assert result["access_token"] == "tok"

def test_parse_user_info():
    provider = DingTalkOAuthProvider()
    result = provider._parse_user_info(
        {},
        {"errcode": 0, "errmsg": "ok", "user_info": {"nick": "李四", "openid": "open_123"}},
    )
    assert result["external_id"] == "open_123"
    assert result["name"] == "李四"
    assert result["provider"] == "dingtalk"
```

```python
# tests/unit/test_wecom_oauth.py
from unittest.mock import patch
from services.auth_provider.wecom_oauth import WeComOAuthProvider

def test_get_authorization_url():
    with patch("services.auth_provider.wecom_oauth.get_settings") as mock:
        mock.return_value.wecom_oauth.corp_id = "ww_test"
        mock.return_value.wecom_oauth.agent_id = "100000"
        mock.return_value.wecom_oauth.redirect_uri = "http://test/callback"
        provider = WeComOAuthProvider()
        url, state = provider.get_authorization_url("mystate")
        assert "open.weixin.qq.com/connect/oauth2/authorize" in url
        assert "appid=ww_test" in url
        assert "agentid=100000" in url

def test_parse_user_info():
    provider = WeComOAuthProvider()
    result = provider._parse_user_info(
        {},
        {"UserId": "wecom_user", "name": "王五", "email": "wang@test.com"},
    )
    assert result["external_id"] == "wecom_user"
    assert result["name"] == "王五"
    assert result["provider"] == "wecom"
```

Run: `uv run pytest tests/unit/test_dingtalk_oauth.py tests/unit/test_wecom_oauth.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write implementations**

`services/auth_provider/dingtalk_oauth.py`:
```python
import httpx
import urllib.parse
from api.config import get_settings
from .base import OAuthProvider, OAuthUserInfo


class DingTalkOAuthProvider(OAuthProvider):
    AUTHORIZE_URL = "https://oapi.dingtalk.com/connect/qrconnect"
    TOKEN_URL = "https://oapi.dingtalk.com/sns/gettoken"
    USER_INFO_URL = "https://oapi.dingtalk.com/sns/getuserinfo_bycode"

    def get_authorization_url(self, state: str = "") -> tuple[str, str]:
        cfg = get_settings().dingtalk_oauth
        params = {
            "appid": cfg.app_id,
            "redirect_uri": cfg.redirect_uri,
            "scope": "openid",
            "state": state,
            "response_type": "code",
        }
        query = urllib.parse.urlencode(params)
        return f"{self.AUTHORIZE_URL}?{query}", state

    def exchange_code(self, code: str) -> dict:
        cfg = get_settings().dingtalk_oauth
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                self.TOKEN_URL,
                json={"appkey": cfg.app_id, "appsecret": cfg.app_secret},
            )
            resp.raise_for_status()
            token_data = resp.json()
            access_token = token_data.get("access_token", "")

            user_resp = client.post(
                self.USER_INFO_URL,
                json={"access_token": access_token, "code": code},
            )
            user_resp.raise_for_status()
            return user_resp.json()

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        # get_user_info is called via exchange_code; this is a no-op for dingtalk
        return OAuthUserInfo(external_id="", provider="dingtalk", name="", email="")

    def _parse_user_info(self, token_data: dict, user_data: dict) -> OAuthUserInfo:
        info = user_data.get("user_info", {})
        return OAuthUserInfo(
            external_id=info.get("openid", ""),
            provider="dingtalk",
            name=info.get("nick", ""),
            email="",
        )
```

`services/auth_provider/wecom_oauth.py`:
```python
import httpx
import urllib.parse
from api.config import get_settings
from .base import OAuthProvider, OAuthUserInfo


class WeComOAuthProvider(OAuthProvider):
    AUTHORIZE_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
    TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
    USER_INFO_URL = "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo"

    def get_authorization_url(self, state: str = "") -> tuple[str, str]:
        cfg = get_settings().wecom_oauth
        params = {
            "appid": cfg.corp_id,
            "redirect_uri": cfg.redirect_uri,
            "response_type": "code",
            "scope": "snsapi_userinfo",
            "state": state,
            "agentid": cfg.agent_id,
        }
        query = urllib.parse.urlencode(params)
        url = f"{self.AUTHORIZE_URL}?{query}#wechat_redirect"
        return url, state

    def exchange_code(self, code: str) -> dict:
        cfg = get_settings().wecom_oauth
        with httpx.Client(timeout=10) as client:
            token_resp = client.get(
                self.TOKEN_URL,
                params={"corpid": cfg.corp_id, "corpsecret": cfg.corp_secret},
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            access_token = token_data.get("access_token", "")

            user_resp = client.get(
                self.USER_INFO_URL,
                params={"access_token": access_token, "code": code},
            )
            user_resp.raise_for_status()
            return user_resp.json()

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        return OAuthUserInfo(external_id="", provider="wecom", name="", email="")

    def _parse_user_info(self, token_data: dict, user_data: dict) -> OAuthUserInfo:
        return OAuthUserInfo(
            external_id=user_data.get("UserId", ""),
            provider="wecom",
            name=user_data.get("name", ""),
            email=user_data.get("email", ""),
        )
```

Run: `uv run pytest tests/unit/test_dingtalk_oauth.py tests/unit/test_wecom_oauth.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add services/auth_provider/dingtalk_oauth.py services/auth_provider/wecom_oauth.py tests/unit/test_dingtalk_oauth.py tests/unit/test_wecom_oauth.py
git commit -m "feat(8): add DingTalk and WeCom OAuth providers"
```

---

## Task 4: Auth Routes

**Files:**
- Create: `api/routes/auth.py`
- Modify: `api/routes/__init__.py`
- Create: `tests/unit/test_auth_routes.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_auth_routes.py
import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock
from api.main import app

@pytest.mark.asyncio
async def test_login_without_provider_returns_providers_page():
    async with AsyncClient(app=app, base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/auth/login")
    assert resp.status_code == 200
    assert "feishu" in resp.text
    assert "dingtalk" in resp.text

@pytest.mark.asyncio
async def test_login_with_feishu_redirects():
    async with AsyncClient(app=app, base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/auth/login", params={"provider": "feishu"})
    assert resp.status_code == 302
    assert "open.feishu.cn" in resp.headers["location"]

@pytest.mark.asyncio
async def test_callback_unknown_provider_returns_400():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/auth/callback", params={"provider": "unknown"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "INVALID_PROVIDER"

@pytest.mark.asyncio
async def test_callback_missing_code_returns_400():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/auth/callback", params={"provider": "feishu"})
    assert resp.status_code == 400
```

Run: `uv run pytest tests/unit/test_auth_routes.py -v`
Expected: FAIL — route not found

- [ ] **Step 2: Write implementation**

`api/routes/auth.py`:
```python
import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from api.config import get_settings
from services.auth_provider.feishu_oauth import FeishuOAuthProvider
from services.auth_provider.dingtalk_oauth import DingTalkOAuthProvider
from services.auth_provider.wecom_oauth import WeComOAuthProvider
from services.session_service import InMemorySessionStore
from services.clickhouse_service import ClickHouseDataService

router = APIRouter(prefix="/auth", tags=["认证"])

_PROVIDERS = {
    "feishu": FeishuOAuthProvider,
    "dingtalk": DingTalkOAuthProvider,
    "wecom": WeComOAuthProvider,
}

_session_store = InMemorySessionStore()
_csrf_store: dict[str, str] = {}  # state -> provider


def _get_or_create_user(provider: str, external_id: str, name: str, email: str) -> dict:
    """查找或创建本地用户，默认角色为财务"""
    ch = ClickHouseDataService()
    # 先查
    existing = ch.execute(
        "SELECT user_id, role, is_active FROM dm.users WHERE external_id = %(eid)s AND provider = %(prov)s",
        {"eid": external_id, "prov": provider},
    )
    if existing:
        row = existing[0]
        return {"user_id": row[0], "role": row[1], "is_active": bool(row[2])}
    # 创建
    import uuid
    user_id = str(uuid.uuid4())
    default_role = "finance"
    ch.execute(
        "INSERT INTO dm.users (user_id, external_id, provider, name, email, role, created_at, updated_at) "
        "VALUES",
        {"user_id": user_id, "external_id": external_id, "provider": provider,
         "name": name, "email": email, "role": default_role,
         "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()},
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
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(""),
    provider: str = Query(""),
):
    # CSRF 验证
    stored_provider = _csrf_store.pop(state, None)
    if not stored_provider:
        raise HTTPException(status_code=400, detail="无效的 state，请重新登录")
    oauth_provider = _PROVIDERS[stored_provider]()

    # 换取 token + 用户信息
    raw_data = oauth_provider.exchange_code(code)
    user_info = oauth_provider._parse_user_info(raw_data, raw_data)

    # 查找/创建本地用户
    local_user = _get_or_create_user(
        provider=stored_provider,
        external_id=user_info["external_id"],
        name=user_info["name"],
        email=user_info["email"],
    )

    if not local_user.get("is_active", True):
        raise HTTPException(status_code=403, detail="账户已被禁用")

    # 创建 session
    session_id = _session_store.create({
        "user_id": local_user["user_id"],
        "external_id": user_info["external_id"],
        "provider": stored_provider,
        "name": user_info["name"],
        "email": user_info["email"],
        "role": local_user["role"],
        "is_active": True,
    })

    # 重定向到首页
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="finboss_session",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=8 * 3600,
    )
    return response


@router.delete("/logout")
async def logout(request: Request, response: Response):
    """登出：删除 session，清除 cookie"""
    session_id = request.cookies.get("finboss_session", "")
    if session_id:
        _session_store.delete(session_id)
    response = Response(status_code=200)
    response.delete_cookie("finboss_session")
    return {"success": True}


@router.get("/me")
async def me(request: Request) -> dict[str, Any]:
    """返回当前用户信息"""
    from starlette.requests import Request as StarletteRequest
    user = request.state.__dict__.get("user") if hasattr(request.state, "__dict__") else None
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return {
        "user_id": user.get("user_id", ""),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "role": user.get("role", ""),
        "provider": user.get("provider", ""),
    }
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/test_auth_routes.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add api/routes/auth.py tests/unit/test_auth_routes.py
git commit -m "feat(8): add auth routes (login/callback/logout/me)"
```

---

## Task 5: Session Middleware

**Files:**
- Create: `api/middleware/session.py`
- Create: `tests/unit/test_session_middleware.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_session_middleware.py
from unittest.mock import MagicMock
from api.middleware.session import SessionMiddleware, requires_auth, PUBLIC_PATHS

def test_public_paths():
    assert "/health" in PUBLIC_PATHS
    assert "/auth/login" in PUBLIC_PATHS
    assert "/auth/callback" in PUBLIC_PATHS
    assert "/docs" in PUBLIC_PATHS

def test_requires_auth_public_paths():
    assert requires_auth("/api/v1/ar/summary") is True
    assert requires_auth("/health") is False
    assert requires_auth("/auth/login") is False
    assert requires_auth("/api/v1/ai/health") is False

async def test_session_injected_into_scope():
    from services.session_service import session_store, InMemorySessionStore
    store = InMemorySessionStore()
    sid = store.create({"user_id": "u1", "role": "admin", "name": "test"})
    scope = {
        "type": "http",
        "path": "/api/v1/ar/summary",
        "headers": [(b"cookie", f"finboss_session={sid}".encode())],
        "state": {},
    }
    receive = MagicMock()
    send = MagicMock()
    middleware = SessionMiddleware(app=MagicMock(), session_store=store)
    await middleware(scope, receive, send)
    assert scope["state"].get("user") is not None
    assert scope["state"]["user"]["user_id"] == "u1"
```

Run: `uv run pytest tests/unit/test_session_middleware.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write implementation**

`api/middleware/session.py`:
```python
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/login",
    "/auth/callback",
    "/api/v1/ai/health",
    "/feishu/events",
}


def requires_auth(path: str) -> bool:
    """不在白名单中的路径需要认证"""
    return not any(
        path == p or path.startswith(p + "/") for p in PUBLIC_PATHS
    )


def parse_cookies(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
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
            response = RedirectResponse(url="/auth/login", status_code=302)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
```

Run: `uv run pytest tests/unit/test_session_middleware.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add api/middleware/session.py tests/unit/test_session_middleware.py
git commit -m "feat(8): add SessionMiddleware"
```

---

## Task 6: Permission Middleware

**Files:**
- Create: `api/middleware/permission.py`
- Create: `tests/unit/test_permission_middleware.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_permission_middleware.py
from unittest.mock import MagicMock
from api.middleware.permission import PermissionMiddleware, ROLE_PERMISSIONS

def test_admin_can_access_all():
    assert ROLE_PERMISSIONS["admin"]["ar"]["read"] is True
    assert ROLE_PERMISSIONS["admin"]["ar"]["write"] is True
    assert ROLE_PERMISSIONS["admin"]["admin"]["write"] is True

def test_finance_cannot_write_ar():
    assert ROLE_PERMISSIONS["finance"]["ar"]["read"] is True
    assert ROLE_PERMISSIONS["finance"]["ar"]["write"] is False

def test_finance_cannot_access_admin():
    assert ROLE_PERMISSIONS["finance"]["admin"]["read"] is False
    assert ROLE_PERMISSIONS["finance"]["admin"]["write"] is False

def test_ops_cannot_access_ar():
    assert ROLE_PERMISSIONS["ops"]["ar"]["read"] is False
    assert ROLE_PERMISSIONS["ops"]["ar"]["write"] is False

async def test_forbidden_returns_403():
    scope = {
        "type": "http",
        "path": "/api/v1/admin/config",
        "method": "PUT",
        "state": {"user": {"role": "finance", "name": "张三"}},
    }
    send_calls = []
    async def fake_send(msg):
        send_calls.append(msg)
    receive = MagicMock()
    middleware = PermissionMiddleware(app=MagicMock())
    await middleware(scope, receive, fake_send)
    assert any(c.get("status") == 403 for c in send_calls)
```

Run: `uv run pytest tests/unit/test_permission_middleware.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write implementation**

`api/middleware/permission.py`:
```python
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
```

Run: `uv run pytest tests/unit/test_permission_middleware.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add api/middleware/permission.py tests/unit/test_permission_middleware.py
git commit -m "feat(8): add PermissionMiddleware with RBAC matrix"
```

---

## Task 7: Admin Routes + User Service

**Files:**
- Create: `api/routes/admin.py`
- Create: `services/user_service.py`
- Create: `tests/unit/test_admin_routes.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_admin_routes.py
import pytest
from httpx import AsyncClient
from unittest.mock import patch
from api.main import app

def _admin_headers():
    return {"Cookie": "finboss_session=admin_session"}

@pytest.mark.asyncio
async def test_list_users_requires_admin():
    with patch("api.routes.admin._require_admin") as mock:
        mock.return_value = {"user_id": "u1", "role": "admin"}
        async with AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.get("/admin/users", headers=_admin_headers())
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_update_user_role():
    with patch("api.routes.admin._require_admin") as mock:
        mock.return_value = {"user_id": "u1", "role": "admin"}
        with patch("services.user_service.ClickHouseDataService") as mock_ch:
            mock_instance = MagicMock()
            mock_instance.execute.return_value = []
            mock_ch.return_value = mock_instance
            async with AsyncClient(app=app, base_url="http://test") as ac:
                resp = await ac.put(
                    "/admin/users/u123/role",
                    json={"role": "sales_manager"},
                    headers=_admin_headers(),
                )
    assert resp.status_code in (200, 404)  # 404 if user doesn't exist
```

Run: `uv run pytest tests/unit/test_admin_routes.py -v`
Expected: FAIL — module not found

- [ ] **Step 2: Write services/user_service.py**

```python
from datetime import datetime
from typing import Any
from services.clickhouse_service import ClickHouseDataService


class UserService:
    def list_users(self) -> list[dict[str, Any]]:
        ch = ClickHouseDataService()
        rows = ch.execute(
            "SELECT user_id, external_id, provider, name, email, role, is_active, created_at "
            "FROM dm.users ORDER BY created_at DESC LIMIT 100"
        )
        return [
            {
                "user_id": r[0], "external_id": r[1], "provider": r[2],
                "name": r[3], "email": r[4], "role": r[5],
                "is_active": bool(r[6]), "created_at": r[7].isoformat() if r[7] else "",
            }
            for r in rows
        ]

    def update_user_role(self, user_id: str, role: str) -> bool:
        ch = ClickHouseDataService()
        ch.execute(
            "ALTER TABLE dm.users UPDATE role = %(role)s, updated_at = %(now)s "
            "WHERE user_id = %(uid)s",
            {"uid": user_id, "role": role, "now": datetime.utcnow()},
        )
        return True

    def list_roles(self) -> list[dict[str, str]]:
        ch = ClickHouseDataService()
        rows = ch.execute("SELECT role_id, role_name, desc FROM dm.roles ORDER BY role_id")
        return [{"role_id": r[0], "role_name": r[1], "desc": r[2] or ""} for r in rows]
```

- [ ] **Step 3: Write api/routes/admin.py**

```python
from fastapi import APIRouter, HTTPException, Request

from services.user_service import UserService

router = APIRouter(prefix="/admin", tags=["系统管理"])


def _require_admin(request: Request) -> dict:
    """要求当前用户是管理员，否则抛出 403"""
    user = request.state.__dict__.get("user") if hasattr(request.state, "__dict__") else None
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


@router.get("/roles")
async def list_roles(request: Request):
    _require_admin(request)
    svc = UserService()
    return {"roles": svc.list_roles()}


@router.get("/users")
async def list_users(request: Request):
    _require_admin(request)
    svc = UserService()
    return {"users": svc.list_users()}


@router.put("/users/{user_id}/role")
async def update_user_role(request: Request, user_id: str, role: str):
    _require_admin(request)
    svc = UserService()
    svc.update_user_role(user_id, role)
    return {"success": True, "user_id": user_id, "role": role}
```

Run: `uv run pytest tests/unit/test_admin_routes.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add api/routes/admin.py services/user_service.py tests/unit/test_admin_routes.py
git commit -m "feat(8): add admin routes and user service"
```

---

## Task 8: Main.py Integration + Remove API Key Auth

**Files:**
- Modify: `api/main.py`
- Modify: `api/dependencies.py`
- Modify: `.env.example`

- [ ] **Step 1: Read current main.py**

Read `api/main.py` from the worktree.

**Required changes:**

1. **Remove** the `AuthMiddleware` registration (the API Key check — lines added in Phase 7c)
2. **Remove** the `RateLimitMiddleware` (Phase 8 keeps rate limiting from Phase 7c — check with user) — **keep RateLimitMiddleware**
3. **Add** new imports:
```python
from api.middleware.session import SessionMiddleware
from api.middleware.permission import PermissionMiddleware
```

4. **Add** after CORSMiddleware (keep existing middlewares, add session + permission):
```python
    # Session + Permission middlewares
    app.add_middleware(PermissionMiddleware)
    app.add_middleware(SessionMiddleware)
```

5. **Remove** the inline `@app.get("/health")` health check endpoint (now in `api/routes/health.py` from Phase 7c — but we already replaced it in Phase 7c, so just ensure it's not duplicated)

6. **Add** router registrations:
```python
    from api.routes.auth import router as auth_router
    from api.routes.admin import router as admin_router
    app.include_router(auth_router)
    app.include_router(admin_router)
```

- [ ] **Step 2: Update .env.example**

Read `.env.example`. Add new section at end:

```
# Phase 8: OAuth SSO Configuration

## Feishu OAuth
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_REDIRECT_URI=https://finboss.example.com/auth/callback
FEISHU_SCOPE=contact:user.avatar:readonly contact:user.email:readonly

## DingTalk OAuth
DINGTALK_APP_ID=dingxxxxxxxxxxxxxxxx
DINGTALK_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DINGTALK_REDIRECT_URI=https://finboss.example.com/auth/callback

## WeCom OAuth
WECOM_CORP_ID=wwxxxxxxxxxxxxxxxx
WECOM_CORP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WECOM_AGENT_ID=1000000
WECOM_REDIRECT_URI=https://finboss.example.com/auth/callback
```

- [ ] **Step 3: Verify tests still pass**

Run: `uv run pytest tests/unit/test_session_middleware.py tests/unit/test_permission_middleware.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add api/main.py api/dependencies.py .env.example
git commit -m "feat(8): integrate session+permission middleware, add auth/admin routes"
```

---

## Task 9: DB Init + Integration Tests

**Files:**
- Create: `scripts/phase8_ddl.sql`
- Create: `scripts/init_phase8.py`
- Create: `tests/integration/test_auth_api.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write DDL**

`scripts/phase8_ddl.sql`:
```sql
-- Phase 8: Users + RBAC Schema

-- 用户表
CREATE TABLE IF NOT EXISTS dm.users (
    user_id     String,
    external_id String,
    provider    String,
    name        String,
    email       String,
    role        String DEFAULT '',
    is_active   UInt8  DEFAULT 1,
    created_at  DateTime DEFAULT now(),
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY user_id;

-- 角色表
CREATE TABLE IF NOT EXISTS dm.roles (
    role_id     String,
    role_name   String,
    desc        String DEFAULT '',
    created_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY role_id;

-- 角色权限矩阵
CREATE TABLE IF NOT EXISTS dm.role_permissions (
    role_id     String,
    module      String,
    can_read    UInt8 DEFAULT 0,
    can_write   UInt8 DEFAULT 0,
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (role_id, module);
```

- [ ] **Step 2: Write init script**

`scripts/init_phase8.py`:
```python
"""Phase 8 幂等初始化：users + roles + role_permissions 表及预置数据"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clickhouse_driver import Client
from api.config import get_settings


def run_ddl(client: Client):
    sql_path = os.path.join(os.path.dirname(__file__), "phase8_ddl.sql")
    with open(sql_path) as f:
        for stmt in f.read().split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                client.execute(stmt)
                print(f"  OK: {stmt[:60]}")
            except Exception as e:
                code = str(e).split()[-1].strip("()")
                if code == "42":
                    print(f"  SKIP (exists): {stmt[:60]}")
                else:
                    raise

    # 预置角色
    roles = [
        ("finance", "财务", "AR + AP + 报表全局只读"),
        ("sales_manager", "销售经理", "AR + 报表只读（团队数据）"),
        ("ops", "运营", "预警 + 报表 + 质量读写"),
        ("admin", "系统管理员", "全部模块读写 + 系统配置"),
    ]
    for role_id, role_name, desc in roles:
        try:
            client.execute(
                "INSERT INTO dm.roles (role_id, role_name, desc) VALUES",
                [{"role_id": role_id, "role_name": role_name, "desc": desc}],
            )
            print(f"  INSERT role: {role_id}")
        except Exception:
            pass  # 已存在

    print("Phase 8 init complete.")


if __name__ == "__main__":
    cfg = get_settings().clickhouse
    client = Client(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
    )
    run_ddl(client)
```

- [ ] **Step 3: Write integration test**

`tests/integration/test_auth_api.py`:
```python
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient
from api.main import app


@pytest.mark.asyncio
async def test_health_public_without_session():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ar_requires_session():
    async with AsyncClient(app=app, base_url="http://test", follow_redirects=False) as ac:
        resp = await ac.get("/api/v1/ar/summary")
    # 无 session → 重定向到 /auth/login
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


@pytest.mark.asyncio
async def test_admin_without_session_returns_302():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/admin/users")
    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_login_page_renders():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/auth/login")
    assert resp.status_code == 200
    assert "飞书" in resp.text or "feishu" in resp.text.lower()
```

- [ ] **Step 4: Run integration tests**

Run: `uv run pytest tests/integration/test_auth_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/phase8_ddl.sql scripts/init_phase8.py tests/integration/test_auth_api.py
git commit -m "feat(8): add Phase 8 DDL, init script, and integration tests"
```

---

## Middleware Registration Order

Final middleware stack in `api/main.py`:
```
CORSMiddleware
TracingMiddleware         ← Phase 7c
RateLimitMiddleware       ← Phase 7c
PermissionMiddleware       ← Phase 8 (checks role × module)
SessionMiddleware          ← Phase 8 (resolves user from cookie)
→ routes
```

Note: `AuthMiddleware` (API Key check) is **removed** in Phase 8. All auth is now session-based.

## Notes

- Phase 8 完成后，所有 API 请求都需要通过 SSO session，不再接受 API Key
- Session 存储为进程内内存，多 uvicorn worker 部署需切换 Redis
- 飞书/钉钉/企微 OAuth 需要在对应开放平台提前申请 App 并配置回调地址
