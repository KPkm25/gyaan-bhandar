"""
Structured JSON logging.

Usage:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("Model loaded", extra={"request_id": "abc-123", "duration_ms": 42})
"""
import logging
import json
import sys
from datetime import datetime, timezone

# Fields already present on every LogRecord by default -- anything else
# passed via `extra=` will be picked up automatically and merged in below.
_RESERVED = set(logging.makeLogRecord({}).__dict__.keys())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Pull in anything passed via extra={...} (request_id, duration_ms, etc.)
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def get_logger(name: str = "gyaan_bhandar") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        # Already configured (avoids duplicate handlers on reload)
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger