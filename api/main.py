"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routes import ar, query


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()
    print(f"Starting {settings.app.app_name} v{settings.app.app_version}")
    yield
    print("Shutting down FinBoss")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app.app_name,
        version=settings.app.app_version,
        description="企业财务AI信息化系统 - Phase 1 MVP",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS 配置
    # Phase 1: 允许所有来源（内部使用）；后续接入认证后改为白名单
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(ar.router, prefix="/api/v1/ar", tags=["AR应收"])
    app.include_router(
        query.router,
        prefix="/api/v1/query",
        tags=["数据查询"],
    )

    @app.get("/health")
    async def health_check():
        """健康检查"""
        return {
            "status": "healthy",
            "service": settings.app.app_name,
            "version": settings.app.app_version,
        }

    return app


app = create_app()
