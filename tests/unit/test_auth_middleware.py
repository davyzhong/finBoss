from api.middleware.auth import PUBLIC_PATHS, AuthMiddleware


def test_public_paths():
    """PUBLIC_PATHS must contain health, docs, and feishu event paths."""
    assert "/health" in PUBLIC_PATHS
    assert "/ready" in PUBLIC_PATHS
    assert "/docs" in PUBLIC_PATHS
    assert "/redoc" in PUBLIC_PATHS
    assert "/openapi.json" in PUBLIC_PATHS
    assert "/api/v1/ai/health" in PUBLIC_PATHS
    assert "/feishu/events" in PUBLIC_PATHS


def test_is_public():
    assert AuthMiddleware._is_public("/health") is True
    assert AuthMiddleware._is_public("/ready") is True
    assert AuthMiddleware._is_public("/docs") is True
    assert AuthMiddleware._is_public("/redoc") is True
    assert AuthMiddleware._is_public("/api/v1/ai/health") is True
    assert AuthMiddleware._is_public("/feishu/events") is True
    assert AuthMiddleware._is_public("/api/v1/ar/summary") is False
    assert AuthMiddleware._is_public("/api/v1/quality/anomalies") is False
