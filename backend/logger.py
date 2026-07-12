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


def get_logger(name: str = "gyaan_bhandar") -> "SafeLogger":
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return SafeLogger(logger)


class SafeLogger:
    """
    Thin wrapper around a stdlib Logger that auto-renames any extra={...}
    key that collides with a reserved LogRecord attribute (e.g. 'filename',
    'module', 'message', 'args', 'lineno'...), instead of letting the stdlib
    raise KeyError and crash the process. Reserved-name collisions are logged
    once as a warning so they get noticed and cleaned up over time.
    """

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _sanitize(self, extra):
        if not extra:
            return extra
        clean = {}
        for key, value in extra.items():
            safe_key = f"ctx_{key}" if key in _RESERVED else key
            clean[safe_key] = value
        return clean

    def _log(self, level, msg, extra=None, **kwargs):
        getattr(self._logger, level)(msg, extra=self._sanitize(extra), **kwargs)

    def debug(self, msg, extra=None, **kwargs):
        self._log("debug", msg, extra, **kwargs)

    def info(self, msg, extra=None, **kwargs):
        self._log("info", msg, extra, **kwargs)

    def warning(self, msg, extra=None, **kwargs):
        self._log("warning", msg, extra, **kwargs)

    def error(self, msg, extra=None, **kwargs):
        self._log("error", msg, extra, **kwargs)

    def critical(self, msg, extra=None, **kwargs):
        self._log("critical", msg, extra, **kwargs)