import logging, json, sys
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


def test_json_formatter_with_exc_info():
    formatter = JSONFormatter()
    try:
        raise ValueError("something went wrong")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname="", lineno=0,
        msg="error occurred", args=(), exc_info=exc_info
    )
    result = json.loads(formatter.format(record))
    assert "exception" in result
    assert "ValueError" in result["exception"]
