# tests/unit/conftest.py
# Isolates unit tests from integration test environment pollution
import os

import pytest


@pytest.fixture(autouse=True)
def isolate_env():
    """Clear API_KEYS env var before and after each unit test."""
    original = os.environ.pop("API_KEYS", None)
    from api.config import get_settings

    get_settings.cache_clear()
    yield
    os.environ.pop("API_KEYS", None)
    if original is not None:
        os.environ["API_KEYS"] = original
    get_settings.cache_clear()
