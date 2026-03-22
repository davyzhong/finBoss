# Production Hardening — 设计规格

> **日期**: 2026-03-22
> **目标**: 为 FinBoss 添加生产级可靠性基础设施

---

## 1. API Key 认证

### 配置

`api/config.py` 新增 `APIKeyConfig`：

```python
class APIKeyConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="api_", extra="ignore")
    keys: list[str] = Field(default=[], description="允许的 API Key 列表")
    rate_limit: int = Field(default=100, description="每分钟每 IP 每端点请求数")
```

环境变量：`API_KEYS=key1,key2,key3`

**在 `Settings` 类中注册**（`api/config.py`）：
```python
api_key: APIKeyConfig = Field(default_factory=APIKeyConfig)
```

### 中间件

`api/middleware/auth.py`：

```python
# 白名单路径（无需认证）
PUBLIC_PATHS = {
    "/health", "/ready",
    "/docs", "/redoc", "/openapi.json",
    "/api/v1/ai/health",
    "/feishu/events",
}
```

**逻辑**：
- 请求路径在白名单 → 通过
- 不在白名单 → 检查 `X-API-Key` header
- 匹配 `keys` 列表 → 通过
- 不匹配/缺失 → 返回 401

**错误响应**（401）：
```json
{"success": false, "error": {"code": "UNAUTHORIZED", "message": "Invalid or missing API key"}, "request_id": "abc123"}
```

---

## 2. 统一错误处理（混合方案）

### 自定义异常

`api/exceptions.py`：

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

### 全局 Handler

`api/main.py` 注册：

| 异常类型 | HTTP 状态码 |
|----------|------------|
| `RequestValidationError` | 422 |
| `HTTPException` | 原状态码 |
| `FinBossError` | 500 |
| `Exception` | 500 |

所有 handler 输出统一 JSON 格式，日志带 request_id。

### 路由层规范

- **允许**：`raise HTTPException(...)` / `raise FinBossError(...)`
- **不允许**：`except: pass`、`except Exception: raise`
- 外部服务错误（ClickHouse / Ollama / Milvus）：捕获后 raise 具体业务异常

---

## 3. 请求追踪和 JSON 结构日志

### Tracing 中间件

`api/middleware/tracing.py`：

```python
async def tracing_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

### JSON 结构日志

`api/logging.py`：

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

日志配置在 `api/main.py` 启动时注入 formatter。

---

## 4. 速率限制（固定窗口）

`api/middleware/rate_limit.py`：

```python
from collections import defaultdict
from time import time

# 固定窗口：{ (ip, endpoint): [(timestamp, count)] }
windows: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)

def check_rate_limit(client_ip: str, endpoint: str, limit: int = 100, window: int = 60) -> bool:
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
```

超限返回 429：
```json
{"success": false, "error": {"code": "RATE_LIMITED", "message": "Rate limit exceeded, retry after 60s"}, "request_id": "abc123"}
```

---

## 5. 熔断 — 不做

外部服务通过 timeout 兜底：
- `httpx` 调用：timeout=60s
- ClickHouse 查询：query timeout=30s
- Scheduler 健康检查持续监控各服务状态

---

## 6. 健康检查

**注意**：`api/main.py` 中现有的 inline `/health` 端点需替换为新 router，以避免路由冲突。

### `/health`（存活检查）

`api/routes/health.py`：

```python
@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

极简实现，< 10ms 返回，不检查任何外部依赖。

### `/ready`（就绪检查）

```python
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

超时 5s：`async with asyncio.timeout(5)` 包装各检查。

---

## 7. 统一响应格式

### 成功响应

```json
{"success": true, "data": {...}}
```

### 错误响应

```json
{"success": false, "error": {"code": "QUALITY_ERROR", "message": "质量检查失败"}, "request_id": "abc123"}
```

### 错误码常量

`api/error_codes.py`：

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

---

## 文件变更总览

| 文件 | 操作 |
|------|------|
| `api/config.py` | 新增 `APIKeyConfig` |
| `api/exceptions.py` | 新建 — 自定义异常类 |
| `api/error_codes.py` | 新建 — 错误码常量 |
| `api/logging.py` | 新建 — JSON formatter |
| `api/middleware/auth.py` | 新建 — API Key 认证中间件 |
| `api/middleware/tracing.py` | 新建 — 请求追踪中间件 |
| `api/middleware/rate_limit.py` | 新建 — 固定窗口限流中间件 |
| `api/routes/health.py` | 新建 — `/health`、`/ready` 端点 |
| `api/main.py` | 修改 — 注册中间件和全局异常 handler |
| `api/dependencies.py` | 修改 — 新增 Key 认证依赖 |
| `.env.example` | 修改 — 新增 `API_KEYS`、`API_RATE_LIMIT` |
| `tests/unit/test_rate_limit.py` | 新建 — 固定窗口限流测试 |
| `tests/unit/test_health.py` | 新建 — 健康检查端点测试 |

---

**注意**：
- 限流计数器为**进程内存储**，多 uvicorn worker 进程间不共享。如需跨进程限流，需换 Redis。
- `/health` 响应格式从 `{status, service, version}` 简化为 `{status: "ok"}`，为 breaking change，已有调用方需注意。
- `/ready` 组件检查为同步（Ollama `is_available()` 为同步方法），如需异步改造可在后续迭代。

---

## 依赖关系

- 所有中间件在路由注册前注入（中间件顺序：tracing → auth → rate_limit）
- 健康检查端点 `/health`、`/ready` 在白名单中，无需认证
- JSON 日志 formatter 在 `api/main.py` 启动时配置
