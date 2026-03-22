from api import error_codes


def test_error_code_constants():
    assert error_codes.UNAUTHORIZED == "UNAUTHORIZED"
    assert error_codes.RATE_LIMITED == "RATE_LIMITED"
    assert error_codes.NOT_FOUND == "NOT_FOUND"
    assert error_codes.VALIDATION_ERROR == "VALIDATION_ERROR"
    assert error_codes.INTERNAL_ERROR == "INTERNAL_ERROR"
    assert error_codes.QUALITY_ERROR == "QUALITY_ERROR"
    assert error_codes.DATA_SERVICE_ERROR == "DATA_SERVICE_ERROR"
    assert error_codes.AI_SERVICE_ERROR == "AI_SERVICE_ERROR"
