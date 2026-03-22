import pytest
import os

# Import create_app and get_settings (not app) so fixture can create the app with test env
from api.main import create_app
from api.config import get_settings
from api.dependencies import (
    get_clickhouse_service,
    get_quality_service,
    get_rag_service,
    get_nl_query_service,
    get_attribution_service,
    get_alert_service,
)

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.exceptions import FinBossError, QualityError
from api.error_codes import QUALITY_ERROR


@pytest.fixture(autouse=True)
def setup_test_api_keys():
    """Set API_KEYS env var and recreate app so middleware picks it up."""
    os.environ["API_KEYS"] = "key1,key2,key3"
    # Clear any cached settings
    get_settings.cache_clear()
    for fn in (
        get_clickhouse_service,
        get_quality_service,
        get_rag_service,
        get_nl_query_service,
        get_attribution_service,
        get_alert_service,
    ):
        fn.cache_clear()
    # Create a fresh app with the test API keys
    app = create_app()
    yield app
    # Cleanup
    for fn in (
        get_clickhouse_service,
        get_quality_service,
        get_rag_service,
        get_nl_query_service,
        get_attribution_service,
        get_alert_service,
    ):
        fn.cache_clear()
    get_settings.cache_clear()


def test_validation_error_returns_422(setup_test_api_keys):
    """Invalid query params should return 422."""
    app = setup_test_api_keys
    client = TestClient(app, headers={"X-API-Key": "key1"})
    resp = client.get(
        "/api/v1/ar/customer",
        params={"limit": "not_a_number"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data.get("success") is False
    assert "error" in data
    assert data["error"].get("code") == "VALIDATION_ERROR"
    assert "request_id" in data


def test_finboss_error_returns_500():
    """When FinBossError (or subclass) is raised, should return 500 with its code."""
    from api.exceptions import FinBossError, QualityError
    from api.error_codes import QUALITY_ERROR
    from fastapi.responses import JSONResponse

    test_app = FastAPI()

    @test_app.get("/test-finboss-error")
    async def raise_finboss_error():
        # Use QualityError (subclass of FinBossError) with code QUALITY_ERROR
        raise QualityError("Test quality error").with_traceback(None)

    @test_app.exception_handler(FinBossError)
    async def finboss_handler(request: Request, exc: FinBossError):
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {"code": exc.code, "message": exc.detail or str(exc)},
                "request_id": getattr(request.state, "request_id", ""),
            },
        )

    client = TestClient(test_app)
    resp = client.get("/test-finboss-error")
    assert resp.status_code == 500
    data = resp.json()
    assert data["error"]["code"] == QUALITY_ERROR


def test_main_app_validation_error_has_correct_structure(setup_test_api_keys):
    """Main app's validation handler returns proper error structure."""
    app = setup_test_api_keys
    client = TestClient(app, headers={"X-API-Key": "key1"})
    resp = client.get(
        "/api/v1/ar/customer",
        params={"limit": "not_a_number"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data.get("success") is False
    assert "error" in data
    assert "request_id" in data
