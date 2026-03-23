# Phase 8 平台成熟度 — 设计规格

> **日期**: 2026-03-23
> **目标**: 为 FinBoss 添加多身份提供商 SSO 登录 + 标准 RBAC 权限体系

---

## 1. 目标与范围

### 核心目标
- 支持飞书、钉钉、企业微信三大平台的 OAuth 2.0 SSO 登录
- 标准 RBAC 权限体系（角色 × 权限矩阵）
- Session-based 会话管理（内存存储）
- 移除 API Key 认证，统一使用 Session 认证

### 本期范围（核心模块）
- AR应收 / AP应付 / 报表 / 预警 / 系统配置
- 不含：知识库、归因分析、客户360、业务员映射（后续迭代）

### 非目标
- 多租户（本期为单租户）
- API Key 长期保留
- 数据行级权限过滤（"团队"在权限矩阵中为占位，表示本期不实现行级过滤，销售经理本期只能看到自己负责的数据，后续迭代时再加团队数据隔离逻辑）

---

## 2. 认证架构

### 认证流程

```
用户浏览器
    │
    ▼
GET /auth/login?provider=feishu|dingtalk|wecom
    │
    ▼ 302 重定向
IdP 授权页（飞书/钉钉/企微）
    │
    ▼ 用户授权
GET /auth/callback?code=xxx&provider=xxx
    │
    ▼ 用 code 换 token，获取用户信息
本地用户表：查找/创建用户
    │
    ▼ 写入内存 Session，返回 cookie
浏览器收到 Set-Cookie: finboss_session=xxx
    │
    ▼ 后续请求带 cookie
SessionMiddleware：从 cookie 解析 session
  → 从 session 提取用户信息、角色
  → 注入 request.state.user
  → PermissionMiddleware 检查模块权限
```

### 身份提供商配置

每种 IdP 单独配置，存于 `api/config.py`（对应环境变量）：

| IdP | OAuth 端点 | 字段 |
|------|-----------|------|
| 飞书 | `https://open.feishu.cn/open-apis/authen/v1/authorize` | app_id, app_secret, scopes |
| 钉钉 | `https://oapi.dingtalk.com/sns/gettoken` | app_id, app_secret |
| 企业微信 | `https://qyapi.weixin.qq.com/cgi-bin/gettoken` | corp_id, agent_id, corp_secret |

### Session 管理

- **存储**: 内存 `dict`（`server-side session`）
- **Session ID**: `secrets.token_urlsafe(32)` — 32 字节随机字符串
- **过期**: 8 小时（可配置）
- **Cookie**: `HttpOnly=True`, `SameSite=Lax`, `Secure`（生产环境）
- **数据结构**:

```python
{
    "user_id": "local-uuid",
    "external_id": "飞书 union_id",
    "provider": "feishu",
    "name": "张三",
    "email": "zhangsan@company.com",
    "role": "财务",
    "created_at": datetime,
    "expires_at": datetime,
}
```

### 登出

```
DELETE /auth/logout
  → 从 session store 删除 session_id
  → 清除浏览器 cookie
  → 返回 200
```

---

## 3. RBAC 数据模型

### 数据库 Schema（ClickHouse）

```sql
CREATE TABLE IF NOT EXISTS dm.users (
    user_id     String,
    external_id String,   -- IdP 的 union_id / user_id
    provider    String,   -- feishu | dingtalk | wecom
    name        String,
    email       String,
    role        String,
    is_active   UInt8  DEFAULT 1,
    created_at  DateTime DEFAULT now(),
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY user_id;
```

### RBAC 表

```sql
CREATE TABLE IF NOT EXISTS dm.roles (
    role_id   String,
    role_name String,
    desc      String,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY role_id;

CREATE TABLE IF NOT EXISTS dm.role_permissions (
    role_id     String,
    module      String,
    can_read    UInt8 DEFAULT 0,
    can_write   UInt8 DEFAULT 0,
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (role_id, module);
```

### 预置角色

| role_id | 角色名 | 说明 |
|---------|--------|------|
| `finance` | 财务 | AR + AP + 报表（全局） |
| `sales_manager` | 销售经理 | AR + 报表（团队数据） |
| `ops` | 运营 | 预警管理 + 报表 |
| `admin` | 系统管理员 | 全部模块读写 + 系统配置 |

### 权限矩阵

| 模块 | 路由前缀 | 财务 | 销售经理 | 运营 | 管理员 |
|------|----------|------|----------|------|--------|
| AR应收 | `/api/v1/ar` | 读 | 读（团队） | — | 读写 |
| AP应付 | `/api/v1/ap` | 读 | — | — | 读写 |
| 报表 | `/api/v1/reports` | 读 | 读（团队） | 读 | 读写 |
| 预警 | `/api/v1/alerts` | 读 | 读（团队） | 读写 | 读写 |
| 质量 | `/api/v1/quality` | 读 | — | 读写 | 读写 |
| 系统配置 | `/api/v1/admin` | — | — | — | 读写 |
| 知识库 | `/api/v1/ai/knowledge` | — | — | — | —（本期不做） |

---

## 4. API 端点

### 认证路由（`api/routes/auth.py`）

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/auth/login` | 开始 OAuth 流程，`?provider=feishu\|dingtalk\|wecom` | 无 |
| GET | `/auth/callback` | IdP 回调，处理 token，绑定/创建用户，写 session | 无 |
| DELETE | `/auth/logout` | 登出，清除 session | 需要 |
| GET | `/auth/me` | 返回当前用户信息 + 角色 | 需要 |

### 管理路由（`api/routes/admin.py`）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/admin/roles` | 列出所有角色 | session + 管理员角色 |
| GET | `/admin/users` | 列出所有用户 | session + 管理员角色 |
| PUT | `/admin/users/{id}/role` | 修改用户角色 | session + 管理员角色 |

以上路由均需有效 session（已在白名单中排除），PermissionMiddleware 额外检查 `user.role == "管理员"`。

---

## 5. 中间件设计

### SessionMiddleware

```python
# 公开路径（无需认证）
PUBLIC_PATHS = {
    "/health", "/ready",
    "/docs", "/redoc", "/openapi.json",
    "/auth/login", "/auth/callback",
    "/api/v1/ai/health",
    "/feishu/events",
}


def requires_auth(path: str) -> bool:
    """判断路径是否需要认证（不在白名单中即为需要认证）。"""
    return not any(
        path == p or path.startswith(p + "/") for p in PUBLIC_PATHS
    )


class SessionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cookies = parse_cookies(scope.get("headers", []))
        session_id = cookies.get("finboss_session")

        if session_id and session_id in session_store:
            session = session_store[session_id]
            if session["expires_at"] > datetime.utcnow():
                scope["state"]["user"] = session
            else:
                del session_store[session_id]
                session_id = None

        # 若无 session 且路径需要认证 → 重定向到统一登录页
        if not session_id and requires_auth(scope["path"]):
            await redirect_to_login(scope, receive, send)
            return

        await self.app(scope, receive, send)
```

重定向到 `/auth/login`（不带 provider 参数时显示提供商选择页）。

### PermissionMiddleware

```python
class PermissionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        method = scope.get("method", "GET")
        user = scope["state"].get("user")

        required = permission_matrix.get_permission(path, method)
        if required and not check_permission(user, required):
            await JSONResponse(
                status_code=403,
                content={"success": False, "error": {"code": "FORBIDDEN", "message": "无权访问"}},
            )(scope, receive, send)
            return

        await self.app(scope, receive, send)
```

### 中间件注册顺序

```
CORS → Tracing → RateLimit → Session → Permission
```

### 现有中间件兼容性

Phase 8 上线后，`AuthMiddleware`（API Key 检查）从中间件栈中移除，所有认证统一由 `SessionMiddleware` 处理。

---

## 6. IdP 具体实现

### 飞书 OAuth

```
授权 URL:
GET https://open.feishu.cn/open-apis/authen/v1/authorize
  ?app_id=CLI_xxx
  &redirect_uri=https://finboss.example.com/auth/callback
  &scope=contact:user.avatar:readonly contact:user.email:readonly
  &state={csrf_token}

回调处理:
1. 验证 `state` 参数是否与 SessionMiddleware 预存的 token 匹配（防 CSRF）
2. 用 `code` 换取 `access_token`
3. 用 `access_token` 获取用户信息

**CSRF 防护**: `/auth/login` 生成随机 `state` token，存入 session（`oauth_state`），回调时比对，不匹配则拒绝。
```

### 钉钉 OAuth

```
授权 URL:
GET https://oapi.dingtalk.com/connect/qrconnect
  ?appid=dingtalk_app_id
  &redirect_uri=xxx&scope=openid

回调处理:
POST https://oapi.dingtalk.com/sns/gettoken
  POST body: appid=...&appsecret=...
  → 获取 access_token

POST https://oapi.dingtalk.com/sns/getuserinfo_bycode
  Body: access_token=...&code=回调code
```

### 企业微信 OAuth

```
授权 URL:
GET https://open.weixin.qq.com/connect/oauth2/authorize
  ?appid=ww_xxx&redirect_uri=xxx
  &response_type=code&scope=snsapi_userinfo#wechat_redirect

回调处理:
GET https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=...&corpsecret=...
  → 获取 access_token

GET https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo?access_token=...&code=回调code
```

---

## 7. Session 存储

```python
# api/session_store.py
from datetime import datetime, timedelta
from secrets import token_urlsafe
from typing import Optional

# 内存存储（开发用）
# 生产环境可替换为 RedisSessionStore
session_store: dict[str, dict] = {}


class SessionStore:
    def create(self, user_info: dict, ttl_hours: int = 8) -> str:
        session_id = token_urlsafe(32)
        self.session_store[session_id] = {
            **user_info,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=ttl_hours),
        }
        return session_id

    def get(self, session_id: str) -> Optional[dict]:
        session = self.session_store.get(session_id)
        if session and session["expires_at"] > datetime.utcnow():
            return session
        # 被动清理：过期 session 被访问时删除（节省内存）
        self.session_store.pop(session_id, None)
        return None

    def delete(self, session_id: str) -> None:
        self.session_store.pop(session_id, None)
```

---

## 8. 文件变更总览

| 文件 | 操作 |
|------|------|
| `api/routes/auth.py` | 新建 — 认证路由（login/callback/logout/me） |
| `api/routes/admin.py` | 新建 — 管理员路由（roles/users） |
| `api/middleware/session.py` | 新建 — SessionMiddleware |
| `api/middleware/permission.py` | 新建 — PermissionMiddleware |
| `api/middleware/auth.py` | 修改 — 移除 API Key 检查逻辑（保留白名单） |
| `api/config.py` | 新增 FeishuOAuthConfig / DingTalkOAuthConfig / WeComOAuthConfig |
| `api/dependencies.py` | 新增 `get_current_user` 依赖 |
| `api/main.py` | 注册新中间件，移除 API Key 中间件 |
| `schemas/user.py` | 新建 — User / Role / RolePermission Pydantic 模型 |
| `services/session_service.py` | 新建 — SessionStore 类 |
| `services/auth_provider/` | 新建 — feishu_oauth.py / dingtalk_oauth.py / wecom_oauth.py |
| `scripts/phase8_ddl.sql` | 新建 — users/roles/role_permissions DDL |
| `scripts/init_phase8.py` | 新建 — 幂等初始化脚本（预置角色） |
| `.env.example` | 新增三种 IdP 的 OAuth 配置 |
| `tests/unit/test_session_middleware.py` | 新建 |
| `tests/unit/test_permission_middleware.py` | 新建 |
| `tests/unit/test_auth_routes.py` | 新建 |
| `tests/integration/test_auth_api.py` | 新建 |

---

## 9. 依赖关系

- `SessionMiddleware` 在 `PermissionMiddleware` 之前执行（先解析用户，再检查权限）
- `SessionMiddleware` 依赖 `SessionStore` 实例
- 各 IdP OAuth 模块独立，无相互依赖
- 用户表在首次登录时自动创建，无需手动预置
- 角色表由 `init_phase8.py` 预置

---

## 10. 注意事项

- Session 为进程内存储，多 uvicorn worker 共享同一内存（单进程）；如需多进程部署，需切换到 Redis
- Session 过期清理为被动模式（`get()` 时删除过期项），大量过期未访问的 session 会轻微占用内存；8小时 TTL 下可接受
- API Key 在 Phase 8 上线后立即失效，所有客户端需迁移到 session cookie 方式
- 钉钉/企微的 OAuth scope 需在对应开放平台申请并审核
- 飞书用户 union_id 在同一企业内唯一，跨企业需额外处理
