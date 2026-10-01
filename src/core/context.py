"""Multi-tenancy context management using Python standard ContextVar."""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token

# Global ContextVar tracking current organization / tenant ID per execution flow
current_tenant_id: ContextVar[int | None] = ContextVar(
    "current_tenant_id", default=None
)


def get_current_tenant_id() -> int | None:
    """Retrieve the active tenant ID from the current asynchronous context."""
    return current_tenant_id.get()


def set_current_tenant_id(tenant_id: int | None) -> Token[int | None]:
    """Explicitly set the active tenant ID in the current execution flow.

    Returns a ContextVar Token that must be used to restore the previous state.
    """
    return current_tenant_id.set(tenant_id)


def reset_current_tenant_id(token: Token[int | None]) -> None:
    """Restore previous tenant ID using the token returned by set_current_tenant_id."""
    current_tenant_id.reset(token)


@contextmanager
def tenant_context(tenant_id: int | None) -> Generator[None, None, None]:
    """Context manager to safely bind a tenant ID for a code block.

    Guarantees that the previous tenant ID is restored upon exit, even if
    an exception is raised within the block.

    Example:
        with tenant_context(tenant_id=101):
            await do_tenant_work()
    """
    token = set_current_tenant_id(tenant_id)
    try:
        yield
    finally:
        reset_current_tenant_id(token)


# Global ContextVar tracking active request / correlation ID per execution flow
current_request_id: ContextVar[str | None] = ContextVar(
    "current_request_id", default=None
)


def get_current_request_id() -> str | None:
    """Retrieve the active request ID from the current asynchronous context."""
    return current_request_id.get()


def set_current_request_id(request_id: str | None) -> Token[str | None]:
    """Explicitly set the active request ID in the current execution flow.

    Returns a ContextVar Token that must be used to restore the previous state.
    """
    return current_request_id.set(request_id)


def reset_current_request_id(token: Token[str | None]) -> None:
    """Restore previous request ID using the token."""
    current_request_id.reset(token)


@contextmanager
def request_id_context(request_id: str | None) -> Generator[None, None, None]:
    """Context manager to safely bind a request ID for a code block.

    Guarantees that the previous request ID is restored upon exit, even if
    an exception is raised within the block.
    """
    token = set_current_request_id(request_id)
    try:
        yield
    finally:
        reset_current_request_id(token)
