"""ARQ Worker configuration and lifecycle orchestration."""

import logging
from collections.abc import Sequence
from typing import Any, cast

from arq.connections import RedisSettings
from arq.cron import CronJob, cron
from arq.typing import WorkerCoroutine
from arq.worker import Function, func

from src.core.config import get_settings
from src.core.database import async_session_factory, engine
from src.core.valkey import close_valkey_pool, get_valkey_pool
from src.worker.tasks import (
    on_job_failure,
    ping_task,
    reconciliar_fila_orphans_task,
    resolver_ring_timeout_task,
)

logger = logging.getLogger("medisync.worker")


def create_redis_settings() -> RedisSettings:
    """Create RedisSettings matching application Valkey configuration."""
    settings = get_settings()
    return RedisSettings(
        host=settings.VALKEY_HOST,
        port=settings.VALKEY_PORT,
        conn_timeout=int(settings.VALKEY_CONNECT_TIMEOUT),
        max_connections=settings.VALKEY_MAX_CONNECTIONS,
    )


async def startup(ctx: dict[Any, Any]) -> None:
    """Initialize shared connections in worker context upon startup."""
    settings = get_settings()
    ctx["settings"] = settings
    ctx["db_engine"] = engine
    ctx["db_session_factory"] = async_session_factory
    ctx["valkey_pool"] = get_valkey_pool()
    logger.info(
        "ARQ worker started successfully. DB pool_size=%d, Valkey URL=%s",
        settings.DB_POOL_SIZE,
        settings.async_valkey_url,
    )


async def shutdown(ctx: dict[Any, Any]) -> None:
    """Dispose of shared connection pools upon worker shutdown."""
    logger.info("ARQ worker shutting down gracefully...")
    await close_valkey_pool()
    await engine.dispose()
    logger.info("ARQ worker connection pools disposed.")


class WorkerSettings:
    """ARQ Worker configuration class for background job processing."""

    _app_settings = get_settings()

    functions: Sequence[Function | WorkerCoroutine] = [
        func(cast("Any", ping_task)),
        func(
            cast("Any", resolver_ring_timeout_task),
            name="resolver_ring_timeout_task",
        ),
        func(
            cast("Any", reconciliar_fila_orphans_task),
            name="reconciliar_fila_orphans_task",
        ),
    ]
    cron_jobs: Sequence[CronJob] = [
        cron(
            cast("Any", reconciliar_fila_orphans_task),
            second=0,
            run_at_startup=False,
            name="reconciliar_fila_orphans_cron",
        ),
    ]
    on_startup = staticmethod(startup)
    on_shutdown = staticmethod(shutdown)
    on_job_failure = staticmethod(on_job_failure)

    redis_settings: RedisSettings = create_redis_settings()
    queue_name: str = _app_settings.ARQ_QUEUE_NAME

    max_jobs: int = _app_settings.ARQ_MAX_JOBS
    job_timeout: int = _app_settings.ARQ_JOB_TIMEOUT
    keep_result: int = _app_settings.ARQ_KEEP_RESULT
    job_completion_wait: int = _app_settings.ARQ_JOB_COMPLETION_WAIT

    health_check_key: str = _app_settings.ARQ_HEALTH_CHECK_KEY
    health_check_interval: int = _app_settings.ARQ_HEALTH_CHECK_INTERVAL
    handle_signals: bool = True
