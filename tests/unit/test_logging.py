import json
import logging

from src.core.context import request_id_context, tenant_context
from src.core.logging import JSONFormatter


def test_json_formatter_standard_fields():
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


def test_json_formatter_with_contextvars():
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

    with request_id_context("req-999"), tenant_context(42):
        output = formatter.format(record)
        data = json.loads(output)
        assert data["request_id"] == "req-999"
        assert data["tenant_id"] == 42
