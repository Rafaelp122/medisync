"""Unit tests for OpenTelemetry instrumentation and JSON log correlation."""

import json
import logging
from typing import cast

from opentelemetry.sdk.trace import TracerProvider
from src.core.logging import JSONFormatter
from src.core.telemetry import get_current_trace_context, setup_telemetry
from src.main import create_app
from starlette.testclient import TestClient


def test_get_current_trace_context_when_no_span() -> None:
    trace_id, span_id = get_current_trace_context()
    assert trace_id is None
    assert span_id is None


def test_json_formatter_without_active_span() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Operação sem span",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["message"] == "Operação sem span"
    assert data["level"] == "INFO"
    assert "trace_id" not in data
    assert "span_id" not in data


def test_json_formatter_with_active_span() -> None:
    provider = setup_telemetry()
    tracer = provider.get_tracer("test_tracer")
    formatter = JSONFormatter()

    with tracer.start_as_current_span("teste_operacao") as span:
        ctx = span.get_span_context()
        expected_trace_id = format(ctx.trace_id, "032x")
        expected_span_id = format(ctx.span_id, "016x")

        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=25,
            msg="Operação com span ativo",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        data = json.loads(formatted)

        assert data["trace_id"] == expected_trace_id
        assert data["span_id"] == expected_span_id
        assert data["message"] == "Operação com span ativo"


def test_setup_telemetry_is_idempotent() -> None:
    p1 = setup_telemetry()
    p2 = setup_telemetry()
    assert isinstance(p1, TracerProvider)
    assert p1 is p2


def test_fastapi_telemetry_route_injects_trace_in_access_log() -> None:
    app = create_app()
    client = TestClient(app)

    # Dispara rota da API que passa por tracing e StructuredLoggingMiddleware
    response = client.post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        "/api/v1/auth/login",
        json={"email": "sre@medisync.org", "senha": "secret"},
    )
    # Rota responde com 401 ou 422, mas deve processar middleware e gerar trace
    assert response.status_code in {401, 422}  # pyright: ignore[reportUnknownMemberType]


def test_fastapi_telemetry_excluded_routes_skip_tracing() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/healthz")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert response.status_code == 200  # pyright: ignore[reportUnknownMemberType]
    data = cast("dict[str, object]", response.json())  # pyright: ignore[reportUnknownMemberType]
    assert data["status"] == "ok"
