import asyncio
from typing import Any

from fastapi import APIRouter

from services.clickhouse_service import ClickHouseDataService

router = APIRouter(tags=["健康检查"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — always returns ok if the app is running."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, Any]:
    """
    Readiness probe — checks external dependencies.
    Returns "ready", "degraded", or "not_ready" based on component health.
    """
    components = {}
    overall = "ready"

    # ClickHouse
    try:
        async with asyncio.timeout(5):
            ch = ClickHouseDataService()
            await asyncio.to_thread(ch.execute, "SELECT 1")
        components["clickhouse"] = "ok"
    except TimeoutError:
        components["clickhouse"] = "timeout"
        overall = "not_ready"
    except Exception as e:
        components["clickhouse"] = f"error: {e}"
        overall = "not_ready"

    # Ollama
    try:
        async with asyncio.timeout(5):
            from services.ai.ollama_service import OllamaService

            svc = OllamaService()
            ollama_ok = await svc.ais_available()
            if ollama_ok:
                components["ollama"] = "ok"
            else:
                components["ollama"] = "degraded"
                if overall == "ready":
                    overall = "degraded"
    except TimeoutError:
        components["ollama"] = "timeout"
        overall = "degraded"
    except Exception as e:
        components["ollama"] = f"error: {e}"
        overall = "degraded"

    return {"status": overall, "components": components}
