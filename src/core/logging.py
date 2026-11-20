"""Structured JSON logging configuration, formatter, and request_id ContextVar."""

import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any, cast

from src.core.telemetry import get_current_trace_context

# Global ContextVar tracking active request / correlation ID per execution flow
current_request_id: ContextVar[str | None] = ContextVar(
    "current_request_id", default=None
)


def get_current_request_id() -> str | None:
    """Retrieve the active request ID from the current asynchronous context."""
    return current_request_id.get()


def set_current_request_id(request_id: str | None) -> Token[str | None]:
    """Explicitly set the active request ID in the current execution flow."""
    return current_request_id.set(request_id)


def reset_current_request_id(token: Token[str | None]) -> None:
    """Restore previous request ID using the token."""
    current_request_id.reset(token)


@contextmanager
def request_id_context(request_id: str | None) -> Generator[None, None, None]:
    """Context manager to safely bind a request ID for a code block."""
    token = set_current_request_id(request_id)
    try:
        yield
    finally:
        reset_current_request_id(token)


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include active request correlation contextvar if bound
        req_id = get_current_request_id()
        if req_id is not None:
            log_entry["request_id"] = req_id

        # Include OpenTelemetry trace context if active
        trace_id, span_id = get_current_trace_context()
        if trace_id is not None:
            log_entry["trace_id"] = trace_id
        if span_id is not None:
            log_entry["span_id"] = span_id

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
