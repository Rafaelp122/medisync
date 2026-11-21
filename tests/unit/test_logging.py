"""Unit tests for JSON structured logging and request_id ContextVar management."""

import json
import logging

from src.core.logging import (
    JSONFormatter,
    current_request_id,
    get_current_request_id,
    request_id_context,
    reset_current_request_id,
    set_current_request_id,
)


def test_json_formatter_standard_fields() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Sample log message",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "test_logger"
    assert data["message"] == "Sample log message"
    assert "timestamp" in data
    assert "tenant_id" not in data


def test_json_formatter_with_contextvars() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Contextual log message",
        args=(),
        exc_info=None,
    )

    with request_id_context("req-999"):
        output = formatter.format(record)
        data = json.loads(output)
        assert data["request_id"] == "req-999"
        assert "tenant_id" not in data


def test_request_id_context_lifecycle() -> None:
    """Validate request ID setting and resetting."""
    assert get_current_request_id() is None
    assert current_request_id.get() is None

    token = set_current_request_id("req-123")
    assert get_current_request_id() == "req-123"

    reset_current_request_id(token)
    assert get_current_request_id() is None


def test_request_id_context_manager() -> None:
    """Validate that request_id_context manager safely binds and restores request ID."""
    assert get_current_request_id() is None

    with request_id_context("req-abc"):
        assert get_current_request_id() == "req-abc"

    assert get_current_request_id() is None


def test_request_id_context_manager_handles_exception() -> None:
    """Validate that request_id_context restores state even when an exception occurs."""
    assert get_current_request_id() is None
    try:
        with request_id_context("req-err"):
            assert get_current_request_id() == "req-err"
            raise RuntimeError("Forced error")
    except RuntimeError:
        pass

    assert get_current_request_id() is None
