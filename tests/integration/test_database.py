"""Integration tests for SQLAlchemy 2.0 AsyncEngine (Psycopg 3).

Validates database connectivity, connection pooling, and RLS session listener.
"""

import asyncio
import socket

import pytest
from sqlalchemy import text
from src.core.context import tenant_context
from src.core.database import async_session_factory, engine, get_db_session


def _is_db_reachable(host: str = "localhost", port: int = 5432) -> bool:
    """Check if the PostgreSQL port is reachable."""
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def check_postgres_running() -> None:
    """Ensure PostgreSQL is accessible before executing database integration tests."""
    if not _is_db_reachable():
        pytest.skip("PostgreSQL (port 5432) is not reachable. Run 'just up' first.")


async def test_database_connection(check_postgres_running: None) -> None:
    """Verify that SQLAlchemy async engine connects to PostgreSQL 17 using Psycopg 3."""
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1;"))
        assert result.scalar() == 1


async def test_session_rls_injection_with_tenant(
    check_postgres_running: None,
) -> None:
    """Verify that beginning a session transaction injects app.current_tenant_id."""
    with tenant_context(4242):
        async with async_session_factory() as session, session.begin():
            result = await session.execute(
                text("SELECT current_setting('app.current_tenant_id', true);")
            )
            assert result.scalar() == "4242"


async def test_session_rls_cleared_without_tenant(
    check_postgres_running: None,
) -> None:
    """Verify that a session transaction without tenant sets an empty string."""
    async with async_session_factory() as session, session.begin():
        result = await session.execute(
            text("SELECT current_setting('app.current_tenant_id', true);")
        )
        assert result.scalar() == ""


async def test_concurrent_sessions_rls_isolation(
    check_postgres_running: None,
) -> None:
    """Verify that concurrent transactions across pool maintain isolated RLS."""

    async def run_tenant_query(tenant_id: int) -> str | None:
        with tenant_context(tenant_id):
            async with async_session_factory() as session, session.begin():
                await asyncio.sleep(0.01)
                result = await session.execute(
                    text("SELECT current_setting('app.current_tenant_id', true);")
                )
                scalar_val = result.scalar()
                return str(scalar_val) if scalar_val is not None else None

    tenant_ids = [1001, 1002, 1003, 1004, 1005]
    results = await asyncio.gather(*(run_tenant_query(tid) for tid in tenant_ids))

    assert results == [str(tid) for tid in tenant_ids]


async def test_get_db_session_dependency(check_postgres_running: None) -> None:
    """Verify that get_db_session yields an operational AsyncSession."""
    session_generator = get_db_session()
    session = await anext(session_generator)
    try:
        result = await session.execute(text("SELECT 10;"))
        assert result.scalar() == 10
    finally:
        await session.close()
