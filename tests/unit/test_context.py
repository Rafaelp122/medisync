"""Unit tests for multi-tenant ContextVar propagation and concurrency isolation."""

import asyncio

from src.core.context import (
    current_request_id,
    current_tenant_id,
    get_current_request_id,
    get_current_tenant_id,
    request_id_context,
    reset_current_request_id,
    reset_current_tenant_id,
    set_current_request_id,
    set_current_tenant_id,
    tenant_context,
)


def test_default_tenant_id_is_none() -> None:
    """Validate that default tenant ID in an uninitialized context is None."""
    assert get_current_tenant_id() is None
    assert current_tenant_id.get() is None


def test_set_and_reset_tenant_id() -> None:
    """Validate explicit setting and resetting using Token."""
    token = set_current_tenant_id(101)
    assert get_current_tenant_id() == 101

    reset_current_tenant_id(token)
    assert get_current_tenant_id() is None


def test_tenant_context_manager() -> None:
    """Validate that tenant_context sets value and reliably restores original state."""
    assert get_current_tenant_id() is None
    with tenant_context(202):
        assert get_current_tenant_id() == 202

    assert get_current_tenant_id() is None


def test_tenant_context_manager_handles_exception() -> None:
    """Validate that tenant_context restores state even when an exception occurs."""
    assert get_current_tenant_id() is None
    try:
        with tenant_context(303):
            assert get_current_tenant_id() == 303
            raise RuntimeError("Forced error")
    except RuntimeError:
        pass

    assert get_current_tenant_id() is None


def test_nested_tenant_contexts() -> None:
    """Validate that nested tenant_context calls restore intermediate states."""
    with tenant_context(10):
        assert get_current_tenant_id() == 10
        with tenant_context(20):
            assert get_current_tenant_id() == 20
        assert get_current_tenant_id() == 10

    assert get_current_tenant_id() is None


async def test_concurrent_tenant_isolation() -> None:
    """Validate that concurrent asyncio coroutines maintain isolated tenant contexts."""

    async def worker(tenant_id: int) -> int | None:
        with tenant_context(tenant_id):
            await asyncio.sleep(0.01)
            return get_current_tenant_id()

    # Launch 50 concurrent coroutines with distinct tenant IDs
    tenant_ids = list(range(1, 51))
    results = await asyncio.gather(*(worker(tid) for tid in tenant_ids))

    assert results == tenant_ids
    assert get_current_tenant_id() is None


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
