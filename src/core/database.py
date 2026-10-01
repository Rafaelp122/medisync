"""Asynchronous database engine, session factory, and RLS listener."""

from collections.abc import AsyncGenerator

from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction

from src.core.config import get_settings
from src.core.context import current_tenant_id

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.async_database_url,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    echo=settings.DB_ECHO,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@event.listens_for(AsyncSession.sync_session_class, "after_begin")
def _set_tenant_rls_on_begin(
    session: Session,
    transaction: SessionTransaction,
    connection: Connection,
) -> None:
    """Inject PostgreSQL session-local variable for Row-Level Security (RLS).

    Executes SELECT set_config('app.current_tenant_id', :tenant_id, true) within
    the active transaction scope (is_local=true). If no tenant is active in context,
    sets the variable to empty string to ensure
    NULLIF(current_setting('app.current_tenant_id', true), '') evaluates to NULL
    and blocks unauthorized cross-tenant data access.
    """
    tenant_id = current_tenant_id.get()
    tenant_val = str(tenant_id) if tenant_id is not None else ""
    connection.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_val},
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an isolated asynchronous SQLAlchemy session for request/task lifecycle."""
    async with async_session_factory() as session:
        yield session
