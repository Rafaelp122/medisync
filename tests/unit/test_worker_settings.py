"""Unit tests for ARQ worker settings, context accessors, and failure telemetry."""

import logging
from typing import Any, cast

import pytest
from redis.asyncio import ConnectionPool, Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from src.core.config import Settings, get_settings
from src.core.valkey import create_arq_redis_settings
from src.worker import settings as worker_settings_mod
from src.worker.context import (
    get_db_session_from_ctx,
    get_session_factory_from_ctx,
    get_valkey_from_ctx,
)
from src.worker.health import check_worker_heartbeat
from src.worker.settings import WorkerSettings, shutdown, startup
from src.worker.tasks import monitored_task, on_job_failure

from tests.doubles import FakeAsyncSession, FakeAsyncSessionFactory, FakeValkey


def test_create_arq_redis_settings() -> None:
    """create_arq_redis_settings should inherit host, port and pool limits."""
    settings = get_settings()
    redis_settings = create_arq_redis_settings()
    assert redis_settings.host == settings.VALKEY_HOST
    assert redis_settings.port == settings.VALKEY_PORT
    assert redis_settings.conn_timeout == 5
    assert redis_settings.max_connections == 50


def test_worker_settings_attributes() -> None:
    """WorkerSettings class should configure queue name, limits, and active tasks."""
    assert WorkerSettings.queue_name == "arq:queue"
    assert WorkerSettings.max_jobs == 20
    assert WorkerSettings.job_timeout == 60
    assert WorkerSettings.job_completion_wait == 10
    assert WorkerSettings.health_check_key == "medisync:worker:health"
    assert WorkerSettings.health_check_interval == 10
    assert WorkerSettings.handle_signals is True
    assert len(WorkerSettings.functions) == 3
    func_names: list[str] = [
        str(getattr(f, "name", getattr(f, "__name__", "")))
        for f in WorkerSettings.functions
    ]
    assert "ping_task" in func_names
    assert "resolver_ring_timeout_task" in func_names
    assert "reconciliar_fila_orphans_task" in func_names
    assert "validar_elegibilidade_task" not in func_names

    assert WorkerSettings.cron_jobs is not None
    assert len(WorkerSettings.cron_jobs) == 1
    cron_names: list[str] = [
        str(getattr(c, "name", "")) for c in WorkerSettings.cron_jobs
    ]
    assert any("reconciliar_fila_orphans" in name for name in cron_names)


@pytest.mark.asyncio
async def test_startup_initializes_logging_telemetry_and_pools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker startup hook initializes logging, OpenTelemetry, and shared pools."""
    logging_calls: list[str] = []
    telemetry_calls: list[bool] = []

    def _fake_setup_logging(*, level: str = "INFO", **kwargs: object) -> None:
        logging_calls.append(level)

    def _fake_setup_telemetry(*args: object, **kwargs: object) -> None:
        telemetry_calls.append(True)

    monkeypatch.setattr("src.worker.settings.setup_logging", _fake_setup_logging)
    monkeypatch.setattr("src.worker.settings.setup_telemetry", _fake_setup_telemetry)

    ctx: dict[str, Any] = {}
    await startup(ctx)

    assert len(logging_calls) == 1
    assert telemetry_calls == [True]
    assert "settings" in ctx
    assert isinstance(ctx["settings"], Settings)
    assert "db_engine" in ctx
    assert isinstance(ctx["db_engine"], AsyncEngine)
    assert "db_session_factory" in ctx
    assert isinstance(ctx["db_session_factory"], async_sessionmaker)
    assert "valkey_pool" in ctx
    assert isinstance(ctx["valkey_pool"], ConnectionPool)


@pytest.mark.asyncio
async def test_shutdown_disposes_pools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Worker shutdown hook should call pool close and engine dispose."""
    ctx: dict[str, Any] = {}
    closed_valkey = 0
    disposed_engine = 0

    async def _fake_close_valkey() -> None:
        nonlocal closed_valkey
        closed_valkey += 1

    async def _fake_dispose_engine() -> None:
        nonlocal disposed_engine
        disposed_engine += 1

    monkeypatch.setattr(worker_settings_mod, "close_valkey_pool", _fake_close_valkey)
    monkeypatch.setattr(worker_settings_mod, "dispose_engine", _fake_dispose_engine)
    await shutdown(ctx)
    assert closed_valkey == 1
    assert disposed_engine == 1


@pytest.mark.asyncio
async def test_context_accessors_with_populated_ctx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Context accessors reuse valkey_client or close pool-owned clients."""
    fake_factory = FakeAsyncSessionFactory(FakeAsyncSession())
    fake_pool = ConnectionPool(host="localhost", port=6379)

    # Case 1: explicit valkey_client injected (not closed by context manager)
    fake_client = FakeValkey()
    ctx_client: dict[str, Any] = {
        "db_session_factory": fake_factory,
        "valkey_client": fake_client,
    }
    assert get_session_factory_from_ctx(ctx_client) is fake_factory
    async with get_valkey_from_ctx(ctx_client) as yielded:
        assert yielded is fake_client

    # Case 2: pool-owned client must be closed via aclose() on exit
    closed = 0

    async def _fake_aclose(self: Redis) -> None:
        nonlocal closed
        closed += 1

    monkeypatch.setattr(Redis, "aclose", _fake_aclose)
    ctx_pool: dict[str, Any] = {
        "db_session_factory": fake_factory,
        "valkey_pool": fake_pool,
    }
    async with get_valkey_from_ctx(ctx_pool) as valkey_client:
        assert isinstance(valkey_client, Redis)
        assert valkey_client.connection_pool is fake_pool
    assert closed == 1


@pytest.mark.asyncio
async def test_context_accessors_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Context accessors fallback to singletons and close owned Redis client."""
    empty_ctx: dict[str, Any] = {}
    factory = get_session_factory_from_ctx(empty_ctx)
    assert isinstance(factory, async_sessionmaker)

    closed = 0

    async def _fake_aclose(self: Redis) -> None:
        nonlocal closed
        closed += 1

    monkeypatch.setattr(Redis, "aclose", _fake_aclose)
    async with get_valkey_from_ctx(empty_ctx) as client:
        assert isinstance(client, Redis)
    assert closed == 1


@pytest.mark.asyncio
async def test_get_db_session_from_ctx() -> None:
    """get_db_session_from_ctx context manager should yield session from factory."""
    fake_session = FakeAsyncSession()
    fake_factory = FakeAsyncSessionFactory(fake_session)

    ctx: dict[str, Any] = {"db_session_factory": fake_factory}
    async with get_db_session_from_ctx(ctx) as session:
        assert session is fake_session


@pytest.mark.asyncio
async def test_on_job_failure_logs_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unhandled failure should log error with full contextual information."""
    ctx: dict[str, Any] = {
        "job_try": 2,
        "enqueue_time": "2026-10-02T18:00:00Z",
        "score": 123456789,
    }
    error = ValueError("Database connection timeout")

    with caplog.at_level(logging.ERROR, logger="medisync.worker"):
        await on_job_failure(ctx, "job_test_123", error)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert "job_test_123" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[1] is error
    assert getattr(record, "job_id", None) == "job_test_123"
    assert getattr(record, "job_try", None) == 2
    assert getattr(record, "error_type", None) == "ValueError"
    assert getattr(record, "error_message", None) == "Database connection timeout"


@pytest.mark.asyncio
async def test_monitored_task_decorator(caplog: pytest.LogCaptureFixture) -> None:
    """monitored_task wrapper should invoke on_job_failure and propagate error."""
    import logging

    @monitored_task
    async def sample_failing_task(ctx: dict[str, Any]) -> None:
        raise RuntimeError("Something went wrong")

    with (
        caplog.at_level(logging.ERROR, logger="medisync.worker"),
        pytest.raises(RuntimeError, match="Something went wrong"),
    ):
        await sample_failing_task({"job_id": "err_1", "job_try": 1})

    assert "job_id=err_1" in caplog.text
    assert "RuntimeError: Something went wrong" in caplog.text


@pytest.mark.asyncio
async def test_check_worker_heartbeat_offline() -> None:
    """Heartbeat check should report offline when key is not found in Valkey."""
    fake_valkey = FakeValkey()

    result = await check_worker_heartbeat(cast("Redis", fake_valkey))
    assert result["status"] == "offline"
    assert result["is_alive"] is False
    assert result["telemetry"] is None


@pytest.mark.asyncio
async def test_check_worker_heartbeat_healthy() -> None:
    """Heartbeat check should parse formatted ARQ telemetry string."""
    fake_valkey = FakeValkey()
    await fake_valkey.set(
        get_settings().ARQ_HEALTH_CHECK_KEY,
        b"Oct-02 18:10:00 j_complete=42 j_failed=1 j_retried=3 j_ongoing=2 queued=5",
    )

    result = await check_worker_heartbeat(cast("Redis", fake_valkey))
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
