"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routes import ai, ar, attribution, feishu, knowledge, query


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

    # 注册路由
    app.include_router(ar.router, prefix="/api/v1/ar", tags=["AR应收"])
    app.include_router(query.router, prefix="/api/v1/query", tags=["数据查询"])
    app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI智能"])
    app.include_router(attribution.router, prefix="/api/v1/attribution", tags=["归因分析"])
    app.include_router(knowledge.router, prefix="/api/v1/ai/knowledge", tags=["知识库"])
    app.include_router(feishu.router, prefix="/api/v1/feishu", tags=["飞书机器人"])

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
