import logging, json
from api.logging import JSONFormatter

def test_json_formatter_output():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="hello", args=(), exc_info=None
    )
    result = json.loads(formatter.format(record))
    assert result["level"] == "INFO"
    assert result["message"] == "hello"
    assert "timestamp" in result
    assert "logger" in result

def test_json_formatter_with_request_id():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="request", args=(), exc_info=None
    )
    record.request_id = "abc123"
    result = json.loads(formatter.format(record))
    assert result["request_id"] == "abc123"
