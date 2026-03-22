import json
import logging


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "level": record.levelname,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record),
            "logger": record.name,
        }
        if hasattr(record, "request_id"):
            data["request_id"] = record.request_id
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data)
