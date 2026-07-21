import json
import logging
from datetime import UTC, datetime
from typing import Any

_STANDARD_LOG_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        context = {
            key: self._serialize(value)
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_ATTRS and not key.startswith("_")
        }
        if context:
            payload["context"] = context

        return json.dumps(payload, separators=(",", ":"))

    @staticmethod
    def _serialize(value: object) -> object:
        try:
            json.dumps(value)
        except TypeError:
            return str(value)
        return value


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[handler],
        force=True,
    )
