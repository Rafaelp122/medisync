"""Worker healthcheck and heartbeat inspection utilities."""

import re
from typing import Any

from redis.asyncio import Redis

from src.core.config import get_settings

_TELEMETRY_PATTERN = re.compile(
    r"^(?P<timestamp>[\w\-: ]+)\s+"
    r"j_complete=(?P<j_complete>\d+)\s+"
    r"j_failed=(?P<j_failed>\d+)\s+"
    r"j_retried=(?P<j_retried>\d+)\s+"
    r"j_ongoing=(?P<j_ongoing>\d+)\s+"
    r"queued=(?P<queued>\d+)"
)


async def check_worker_heartbeat(
    valkey: Redis,
    health_check_key: str | None = None,
) -> dict[str, Any]:
    """Inspect the ARQ worker heartbeat key in Valkey and parse telemetry.

    Returns structured health telemetry indicating whether the worker is
    actively publishing heartbeats or whether the worker instance is offline.
    """
    key = health_check_key or get_settings().ARQ_HEALTH_CHECK_KEY
    raw_val: Any = await valkey.get(key)  # pyright: ignore[reportUnknownMemberType]

    if raw_val is None:
        return {
            "status": "offline",
            "is_alive": False,
            "health_check_key": key,
            "telemetry": None,
        }

    raw_text = raw_val.decode("utf-8") if isinstance(raw_val, bytes) else str(raw_val)

    match = _TELEMETRY_PATTERN.search(raw_text.strip())
    telemetry: dict[str, Any] = {
        "raw": raw_text,
    }

    if match:
        data = match.groupdict()
        telemetry.update(
            {
                "heartbeat_timestamp": data["timestamp"],
                "jobs_complete": int(data["j_complete"]),
                "jobs_failed": int(data["j_failed"]),
                "jobs_retried": int(data["j_retried"]),
                "jobs_ongoing": int(data["j_ongoing"]),
                "jobs_queued": int(data["queued"]),
            }
        )

    return {
        "status": "healthy",
        "is_alive": True,
        "health_check_key": key,
        "telemetry": telemetry,
    }
