"""Integration tests for ARQ worker lifecycle, connection sharing, and heartbeats."""

from typing import Any, cast
from unittest.mock import patch

import pytest
from arq.connections import create_pool
from arq.worker import create_worker, func
from src.core.config import get_settings
from src.worker.health import check_worker_heartbeat
from src.worker.settings import WorkerSettings
from src.worker.tasks import monitored_task

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_arq_worker_executes_ping_task_with_shared_pools() -> None:
    """Worker in burst mode should process ping_task and verify DB and Valkey."""
    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        job = await pool.enqueue_job("ping_task", message="integration-test")
        assert job is not None

        worker = create_worker(
            WorkerSettings,  # pyright: ignore[reportArgumentType]
            burst=True,
        )
        await worker.main()

        result = await job.result(timeout=5)
        assert result == "integration-test:valkey=True:db=True"
        assert worker.jobs_complete >= 1
        assert worker.jobs_failed == 0
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_arq_worker_publishes_heartbeat_key() -> None:
    """Worker should publish telemetry to the configured Valkey heartbeat key."""
    settings = get_settings()
    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        # Clear existing heartbeat key
        await pool.delete(settings.ARQ_HEALTH_CHECK_KEY)

        worker = create_worker(
            WorkerSettings,  # pyright: ignore[reportArgumentType]
            burst=True,
            redis_pool=pool,
        )
        # Force heartbeat check recording
        worker._last_health_check = 0.0  # pyright: ignore[reportPrivateUsage]
        await worker.record_health()

        # Inspect heartbeat via telemetry reader helper
        health = await check_worker_heartbeat(
            pool, health_check_key=settings.ARQ_HEALTH_CHECK_KEY
        )
        assert health["status"] == "healthy"
        assert health["is_alive"] is True
        assert health["telemetry"] is not None
        assert "jobs_complete" in health["telemetry"]
        assert "jobs_queued" in health["telemetry"]

        # Check key TTL is positive
        ttl = await pool.ttl(settings.ARQ_HEALTH_CHECK_KEY)
        assert ttl > 0
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_arq_worker_unhandled_failure_logging() -> None:
    """Unhandled exceptions in tasks should be logged with full context."""

    @monitored_task
    async def deliberate_failing_task(ctx: dict[str, Any]) -> None:
        raise RuntimeError("Controlled catastrophic test failure")

    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        with patch("src.worker.tasks.logger.error") as mock_log:
            job = await pool.enqueue_job("deliberate_failing_task")
            assert job is not None

            worker = create_worker(
                WorkerSettings,  # pyright: ignore[reportArgumentType]
                functions=[
                    func(
                        cast("Any", deliberate_failing_task),
                        name="deliberate_failing_task",
                    )
                ],
                burst=True,
                redis_pool=pool,
            )
            await worker.main()

            assert worker.jobs_failed >= 1
            mock_log.assert_called_once()
            args, kwargs = mock_log.call_args
            assert args[1] == job.job_id
            assert kwargs["extra"]["job_id"] == job.job_id
            assert kwargs["extra"]["error_type"] == "RuntimeError"
            assert (
                kwargs["extra"]["error_message"]
                == "Controlled catastrophic test failure"
            )
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_worker_graceful_shutdown_timeout_configured() -> None:
    """Worker must be configured with a 10s graceful completion wait for signals."""
    worker = create_worker(
        WorkerSettings,  # pyright: ignore[reportArgumentType]
        burst=True,
    )
    assert worker._job_completion_wait == 10  # pyright: ignore[reportPrivateUsage]
    assert worker._handle_signals is True  # pyright: ignore[reportPrivateUsage]
