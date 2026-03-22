import pytest


def test_error_codes_module_loads():
    """Error codes are string constants — verify module loads and constants are strings."""
    from api import error_codes

    expected = {
        "UNAUTHORIZED",
        "RATE_LIMITED",
        "NOT_FOUND",
        "VALIDATION_ERROR",
        "INTERNAL_ERROR",
        "QUALITY_ERROR",
        "DATA_SERVICE_ERROR",
        "AI_SERVICE_ERROR",
    }
    for name in expected:
        val = getattr(error_codes, name)
        assert isinstance(val, str), f"{name} must be a string"
        assert val == name, f"{name} must equal its own name"
