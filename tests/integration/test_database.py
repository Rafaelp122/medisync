"""Integration tests for SQLAlchemy 2.0 AsyncEngine (Psycopg 3).

Validates database connectivity, connection pooling, and concurrent queries.
"""

import asyncio
import socket

import pytest
from sqlalchemy import text
from src.core.database import get_db_session, get_engine, get_session_factory


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
    async with get_engine().connect() as connection:
        result = await connection.execute(text("SELECT 1;"))
        assert result.scalar() == 1


async def test_concurrent_sessions_pool_isolation(
    check_postgres_running: None,
) -> None:
    """Verify that concurrent transactions across the pool execute isolated queries."""

    async def run_query(value: int) -> int | None:
        async with get_session_factory()() as session, session.begin():
            await asyncio.sleep(0.01)
            result = await session.execute(text("SELECT :val"), {"val": value})
            scalar_val = result.scalar()
            return int(scalar_val) if scalar_val is not None else None

    values = [1001, 1002, 1003, 1004, 1005]
    results = await asyncio.gather(*(run_query(val) for val in values))

    assert results == values


async def test_get_db_session_dependency(check_postgres_running: None) -> None:
    """Verify that get_db_session yields an operational AsyncSession."""
    session_generator = get_db_session()
    session = await anext(session_generator)
    try:
        result = await session.execute(text("SELECT 10;"))
        assert result.scalar() == 10
    finally:
        await session.close()
