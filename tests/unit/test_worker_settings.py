"""Unit tests for ARQ worker settings, context accessors, and failure telemetry."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio import ConnectionPool, Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from src.core.config import Settings
from src.worker.context import (
    get_db_engine_from_ctx,
    get_db_session_from_ctx,
    get_session_factory_from_ctx,
    get_settings_from_ctx,
    get_valkey_from_ctx,
)
from src.worker.health import check_worker_heartbeat
from src.worker.settings import (
    WorkerSettings,
    create_redis_settings,
    shutdown,
    startup,
)
from src.worker.tasks import monitored_task, on_job_failure


def test_create_redis_settings() -> None:
    """RedisSettings should inherit host, port and pool limits from Settings."""
    redis_settings = create_redis_settings()
    assert redis_settings.host == "localhost"
    assert redis_settings.port == 6379
    assert redis_settings.conn_timeout == 5
    assert redis_settings.max_connections == 50


def test_worker_settings_attributes() -> None:
    """WorkerSettings class should configure queue name, limits, and functions."""
    assert WorkerSettings.queue_name == "arq:queue"
    assert WorkerSettings.max_jobs == 20
    assert WorkerSettings.job_timeout == 60
    assert WorkerSettings.job_completion_wait == 10
    assert WorkerSettings.health_check_key == "medisync:worker:health"
    assert WorkerSettings.health_check_interval == 10
    assert WorkerSettings.handle_signals is True
    assert len(WorkerSettings.functions) == 2
    func_names: list[str] = [
        str(getattr(f, "name", getattr(f, "__name__", "")))
        for f in WorkerSettings.functions
    ]
    assert "ping_task" in func_names
    assert "resolver_ring_timeout_task" in func_names


@pytest.mark.asyncio
async def test_startup_injects_connection_pools() -> None:
    """Worker startup hook should populate context with shared DB and Valkey pools."""
    ctx: dict[str, Any] = {}
    await startup(ctx)

    assert "settings" in ctx
    assert isinstance(ctx["settings"], Settings)
    assert "db_engine" in ctx
    assert isinstance(ctx["db_engine"], AsyncEngine)
    assert "db_session_factory" in ctx
    assert isinstance(ctx["db_session_factory"], async_sessionmaker)
    assert "valkey_pool" in ctx
    assert isinstance(ctx["valkey_pool"], ConnectionPool)


@pytest.mark.asyncio
async def test_shutdown_disposes_pools() -> None:
    """Worker shutdown hook should call pool close and engine dispose."""
    ctx: dict[str, Any] = {}
    mock_engine = AsyncMock(spec=AsyncEngine)
    with (
        patch(
            "src.worker.settings.close_valkey_pool", new_callable=AsyncMock
        ) as mock_valkey,
        patch("src.worker.settings.engine", mock_engine),
    ):
        await shutdown(ctx)
        mock_valkey.assert_awaited_once()
        mock_engine.dispose.assert_awaited_once()


def test_context_accessors_with_populated_ctx() -> None:
    """Context accessors should prefer context-provided resources."""
    mock_settings = Settings()
    mock_engine = MagicMock(spec=AsyncEngine)
    mock_factory = MagicMock(spec=async_sessionmaker)
    mock_pool = MagicMock(spec=ConnectionPool)
    mock_pool.connection_kwargs = {}

    ctx: dict[str, Any] = {
        "settings": mock_settings,
        "db_engine": mock_engine,
        "db_session_factory": mock_factory,
        "valkey_pool": mock_pool,
    }

    assert get_settings_from_ctx(ctx) is mock_settings
    assert get_db_engine_from_ctx(ctx) is mock_engine
    assert get_session_factory_from_ctx(ctx) is mock_factory

    valkey_client = get_valkey_from_ctx(ctx)
    assert isinstance(valkey_client, Redis)
    assert valkey_client.connection_pool is mock_pool


def test_context_accessors_fallback() -> None:
    """Context accessors should fallback to system singletons if ctx is empty."""
    empty_ctx: dict[str, Any] = {}
    settings = get_settings_from_ctx(empty_ctx)
    assert isinstance(settings, Settings)
    engine = get_db_engine_from_ctx(empty_ctx)
    assert isinstance(engine, AsyncEngine)
    factory = get_session_factory_from_ctx(empty_ctx)
    assert isinstance(factory, async_sessionmaker)
    client = get_valkey_from_ctx(empty_ctx)
    assert isinstance(client, Redis)


@pytest.mark.asyncio
async def test_get_db_session_from_ctx() -> None:
    """get_db_session_from_ctx context manager should yield session from factory."""
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    ctx: dict[str, Any] = {"db_session_factory": mock_factory}
    async with get_db_session_from_ctx(ctx) as session:
        assert session is mock_session


@pytest.mark.asyncio
async def test_on_job_failure_logs_diagnostics() -> None:
    """Unhandled failure should log error with full contextual information."""
    ctx: dict[str, Any] = {
        "job_try": 2,
        "enqueue_time": "2026-10-02T18:00:00Z",
        "score": 123456789,
    }
    error = ValueError("Database connection timeout")

    with patch("src.worker.tasks.logger.error") as mock_log:
        await on_job_failure(ctx, "job_test_123", error)

    mock_log.assert_called_once()
    args, kwargs = mock_log.call_args
    assert args[1] == "job_test_123"
    assert kwargs["exc_info"] is error
    assert kwargs["extra"]["job_id"] == "job_test_123"
    assert kwargs["extra"]["job_try"] == 2
    assert kwargs["extra"]["error_type"] == "ValueError"
    assert kwargs["extra"]["error_message"] == "Database connection timeout"


@pytest.mark.asyncio
async def test_monitored_task_decorator() -> None:
    """monitored_task wrapper should invoke on_job_failure and propagate error."""
    mock_failure = AsyncMock()

    @monitored_task
    async def sample_failing_task(ctx: dict[str, Any]) -> None:
        raise RuntimeError("Something went wrong")

    with patch("src.worker.tasks.on_job_failure", mock_failure):
        with pytest.raises(RuntimeError, match="Something went wrong"):
            await sample_failing_task({"job_id": "err_1"})

        mock_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_worker_heartbeat_offline() -> None:
    """Heartbeat check should report offline when key is not found in Valkey."""
    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.get = AsyncMock(return_value=None)

    result = await check_worker_heartbeat(mock_valkey)
    assert result["status"] == "offline"
    assert result["is_alive"] is False
    assert result["telemetry"] is None


@pytest.mark.asyncio
async def test_check_worker_heartbeat_healthy() -> None:
    """Heartbeat check should parse formatted ARQ telemetry string."""
    mock_valkey = MagicMock(spec=Redis)
    mock_valkey.get = AsyncMock(
        return_value=(
            b"Oct-02 18:10:00 j_complete=42 j_failed=1 j_retried=3 j_ongoing=2 queued=5"
        )
    )

    result = await check_worker_heartbeat(mock_valkey)
    assert result["status"] == "healthy"
    assert result["is_alive"] is True
    telemetry = result["telemetry"]
    assert telemetry is not None
    assert telemetry["jobs_complete"] == 42
    assert telemetry["jobs_failed"] == 1
    assert telemetry["jobs_retried"] == 3
    assert telemetry["jobs_ongoing"] == 2
    assert telemetry["jobs_queued"] == 5
    assert telemetry["heartbeat_timestamp"] == "Oct-02 18:10:00"
