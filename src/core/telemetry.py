"""OpenTelemetry instrumentation setup and trace context helpers."""

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider


def setup_telemetry() -> TracerProvider:
    """Initialize OpenTelemetry TracerProvider if not already configured."""
    current_provider = trace.get_tracer_provider()
    if isinstance(current_provider, TracerProvider):
        return current_provider

    service_name = os.getenv("OTEL_SERVICE_NAME", "medisync-api")
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)
    return provider


def get_current_trace_context() -> tuple[str | None, str | None]:
    """Extract (trace_id, span_id) from current active OpenTelemetry span.

    Returns hex-formatted trace_id (32 chars) and span_id (16 chars) if valid,
    or (None, None) if no active recording span.
    """
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        trace_id = format(ctx.trace_id, "032x")
        span_id = format(ctx.span_id, "016x")
        return trace_id, span_id
    return None, None
