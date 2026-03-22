"""FastAPI 应用入口"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.config import get_settings
from api.error_codes import (
    INTERNAL_ERROR,
    VALIDATION_ERROR,
)
from api.exceptions import FinBossError
from api.logging import JSONFormatter
from api.middleware.auth import AuthMiddleware
from api.middleware.rate_limit import RateLimitMiddleware
from api.middleware.tracing import TracingMiddleware
from api.routes import (
    ai,
    alerts,
    ap,
    ar,
    attribution,
    customer360,
    feishu,
    health,
    knowledge,
    quality,
    query,
    reports,
    salesperson_mapping,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()
    print(f"Starting {settings.app.app_name} v{settings.app.app_version}")

    from services.scheduler_service import start_scheduler, stop_scheduler

    start_scheduler()

    yield

    stop_scheduler()
    print("Shutting down FinBoss")


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors → 422."""
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {"code": VALIDATION_ERROR, "message": str(exc.errors())},
            "request_id": request_id,
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle Starlette HTTP exceptions — pass through original status code."""
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {"code": INTERNAL_ERROR, "message": exc.detail},
            "request_id": request_id,
        },
    )


async def finboss_exception_handler(request: Request, exc: FinBossError):
    """Handle FinBoss business exceptions → 500."""
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {"code": exc.code, "message": exc.detail or str(exc)},
            "request_id": request_id,
        },
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all for unexpected exceptions → 500."""
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {"code": INTERNAL_ERROR, "message": "Internal server error"},
            "request_id": request_id,
        },
    )


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app.app_name,
        version=settings.app.app_version,
        description="企业财务AI信息化系统 - Phase 2 AI",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS 配置：通过 APP_CORS_ORIGINS 环境变量配置，支持逗号分隔多个源
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Tracing: X-Request-ID generation and propagation
    app.add_middleware(TracingMiddleware)

    # API Key 认证
    app.add_middleware(
        AuthMiddleware,
        api_keys=settings.api_key.keys,
    )

    # Rate Limiting
    app.add_middleware(
        RateLimitMiddleware,
        limit=settings.api_key.rate_limit,
    )

    # Configure JSON logging for uvicorn
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logger = logging.getLogger(logger_name)
        if logger.handlers:
            logger.handlers[0].setFormatter(JSONFormatter())

    # 注册路由
    app.include_router(ar.router, prefix="/api/v1/ar", tags=["AR应收"])
    app.include_router(query.router, prefix="/api/v1/query", tags=["数据查询"])
    app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI智能"])
    app.include_router(attribution.router, prefix="/api/v1/attribution", tags=["归因分析"])
    app.include_router(knowledge.router, prefix="/api/v1/ai/knowledge", tags=["知识库"])
    app.include_router(feishu.router, prefix="/api/v1/feishu", tags=["飞书机器人"])
    app.include_router(customer360.router, prefix="/api/v1", tags=["客户360"])
    app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["预警管理"])
    app.include_router(reports.router, prefix="/api/v1/reports", tags=["报告管理"])
    app.include_router(salesperson_mapping.router, prefix="/api/v1/salesperson", tags=["业务员映射"])
    app.include_router(ap.router, prefix="/api/v1/ap", tags=["AP管理"])
    app.include_router(quality.router, prefix="/api/v1/quality", tags=["数据质量"])

    # 挂载静态文件目录用于报告页面（隔离到 /static/reports 避免与根 /static 冲突）
    from pathlib import Path

    static_dir = Path(__file__).parent.parent / "static" / "reports"
    if static_dir.exists():
        app.mount("/static/reports", StaticFiles(directory=str(static_dir)), name="static_reports")

    # Health check endpoints (replaces inline /health)
    app.include_router(health.router)

    # Register global exception handlers
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(FinBossError, finboss_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    return app


app = create_app()
