"""Worker background tasks and unhandled failure telemetry."""

import functools
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Concatenate

from sqlalchemy import text

from src.worker.context import get_db_session_from_ctx, get_valkey_from_ctx

logger = logging.getLogger("medisync.worker")


async def on_job_failure(
    ctx: dict[str, Any],
    job_id: str,
    exc: BaseException,
) -> None:
    """Log unhandled task failures with structured contextual diagnostics."""
    logger.error(
        "ARQ task failed execution: job_id=%s error=%s: %s",
        job_id,
        exc.__class__.__name__,
        str(exc),
        extra={
            "job_id": job_id,
            "job_try": ctx.get("job_try"),
            "enqueue_time": str(ctx.get("enqueue_time")),
            "score": ctx.get("score"),
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
        },
        exc_info=exc,
    )


def monitored_task[**P, R](
    func: Callable[Concatenate[dict[str, Any], P], Coroutine[Any, Any, R]],
) -> Callable[Concatenate[dict[str, Any], P], Coroutine[Any, Any, R]]:
    """Wrap an ARQ task coroutine to automatically capture and log failures."""

    @functools.wraps(func)
    async def wrapper(ctx: dict[str, Any], *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(ctx, *args, **kwargs)
        except Exception as exc:
            job_id = str(ctx.get("job_id", "unknown"))
            await on_job_failure(ctx, job_id, exc)
            raise

    return wrapper


@monitored_task
async def ping_task(ctx: dict[str, Any], message: str = "pong") -> str:
    """Diagnostic task verifying shared connection pool health across services."""
    valkey = get_valkey_from_ctx(ctx)
    valkey_alive = bool(
        await valkey.ping()  # pyright: ignore[reportUnknownMemberType]
    )

    db_alive = False
    async with get_db_session_from_ctx(ctx) as session:
        result = await session.execute(text("SELECT 1"))
        db_alive = result.scalar_one() == 1

    return f"{message}:valkey={valkey_alive}:db={db_alive}"
