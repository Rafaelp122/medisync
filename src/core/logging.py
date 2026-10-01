"""Structured JSON logging configuration and formatter."""

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.core.context import get_current_request_id, get_current_tenant_id


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include active contextvars if bound
        req_id = get_current_request_id()
        if req_id is not None:
            log_entry["request_id"] = req_id

        tenant_id = get_current_tenant_id()
        if tenant_id is not None:
            log_entry["tenant_id"] = tenant_id

        # Merge extra attributes if passed
        raw_extra: object = getattr(record, "extra_fields", None)
        if isinstance(raw_extra, dict):
            extra_dict = cast("dict[str, object]", raw_extra)
            for k, v in extra_dict.items():
                log_entry[k] = v

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with JSONFormatter."""
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on reload
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
