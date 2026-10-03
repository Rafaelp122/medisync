"""Core notification protocols, rate limiting, and adapters."""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from redis.asyncio import Redis


logger: logging.Logger = logging.getLogger("medisync.notifications")

_RATE_LIMIT_LUA_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local data = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil or last_refill == nil then
    tokens = capacity
    last_refill = now
else
    local delta = math.max(0, now - last_refill)
    tokens = math.min(capacity, tokens + (delta * refill_rate))
    last_refill = now
end

if tokens >= requested then
    tokens = tokens - requested
    redis.call("HMSET", key, "tokens", tostring(tokens),
               "last_refill", tostring(last_refill))
    redis.call("EXPIRE", key, ttl)
    return {1, tostring(tokens), "0.0"}
else
    local missing = requested - tokens
    local retry_after = 0.0
    if refill_rate > 0 then
        retry_after = missing / refill_rate
    end
    redis.call("HMSET", key, "tokens", tostring(tokens),
               "last_refill", tostring(last_refill))
    redis.call("EXPIRE", key, ttl)
    return {0, tostring(tokens), tostring(retry_after)}
end
"""


@runtime_checkable
class NotificationPort(Protocol):
    """Abstract port for dispatching SMS and WhatsApp notifications."""

    async def send_sms(self, to: str, message: str) -> bool:
        """Send an SMS text message to the given destination phone number."""
        ...

    async def send_whatsapp(
        self,
        to: str,
        template: str,
        params: dict[str, str] | None = None,
    ) -> bool:
        """Send a WhatsApp notification based on template and variable params."""
        ...


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a token bucket rate limit evaluation."""

    allowed: bool
    remaining_tokens: float
    retry_after_seconds: float


class LoggingNotificationAdapter:
    """Console/logger notification adapter for local testing and open-source deploys.

    Operates without requiring third-party API credentials (e.g. Twilio, Meta, Z-API).
    Maintains an in-memory buffer of dispatched messages for test inspections.
    """

    def __init__(self) -> None:
        self.sent_sms: list[dict[str, Any]] = []
        self.sent_whatsapp: list[dict[str, Any]] = []

    async def send_sms(self, to: str, message: str) -> bool:
        """Log SMS dispatch and record in memory buffer."""
        logger.info("Notification [SMS] sent to %s: %s", to, message)
        self.sent_sms.append(
            {
                "to": to,
                "message": message,
                "sent_at": datetime.now(UTC),
            }
        )
        return True

    async def send_whatsapp(
        self,
        to: str,
        template: str,
        params: dict[str, str] | None = None,
    ) -> bool:
        """Log WhatsApp dispatch and record in memory buffer."""
        effective_params = params or {}
        logger.info(
            "Notification [WhatsApp] sent to %s [template=%s, params=%s]",
            to,
            template,
            effective_params,
        )
        self.sent_whatsapp.append(
            {
                "to": to,
                "template": template,
                "params": effective_params,
                "sent_at": datetime.now(UTC),
            }
        )
        return True

    def clear(self) -> None:
        """Clear recorded in-memory messages."""
        self.sent_sms.clear()
        self.sent_whatsapp.clear()


# Aliases for configuration and readability
ConsoleNotificationAdapter = LoggingNotificationAdapter
FakeNotificationAdapter = LoggingNotificationAdapter


class NotificationRateLimiter:
    """Atomic token bucket rate limiter over Valkey 8.0 with in-memory fallback.

    Prevents notification spam and provider cost spikes per destination number.
    Uses atomic Lua script to eliminate race conditions under concurrent requests.
    """

    def __init__(
        self,
        valkey_client: "Redis | None" = None,
        capacity: int = 5,
        refill_rate_per_second: float = 0.05,
        ttl_seconds: int = 3600,
        key_prefix: str = "ratelimit:notif:",
    ) -> None:
        self._valkey = valkey_client
        self._capacity = max(1, capacity)
        self._refill_rate = max(0.0, refill_rate_per_second)
        self._ttl_seconds = max(1, ttl_seconds)
        self._key_prefix = key_prefix
        # In-memory store fallback when Valkey is not provided:
        # {key: (tokens, last_refill)}
        self._memory_store: dict[str, tuple[float, float]] = {}

    async def check_rate_limit(
        self, destination: str, cost: int = 1
    ) -> RateLimitResult:
        """Evaluate token availability for a destination phone number."""
        key = f"{self._key_prefix}{destination}"
        now = time.time()

        if self._valkey is not None:
            raw_result: Any = await cast(
                "Awaitable[Any]",
                self._valkey.eval(  # pyright: ignore[reportUnknownMemberType]
                    _RATE_LIMIT_LUA_SCRIPT,
                    1,
                    key,
                    str(self._capacity),
                    str(self._refill_rate),
                    str(now),
                    str(cost),
                    str(self._ttl_seconds),
                ),
            )
            return self._parse_valkey_result(raw_result)

        return self._evaluate_in_memory(key, now, cost)

    async def acquire(self, destination: str, cost: int = 1) -> bool:
        """Convenience method returning True if allowed, False if rate limited."""
        result = await self.check_rate_limit(destination, cost=cost)
        return result.allowed

    def _parse_valkey_result(self, raw_result: Any) -> RateLimitResult:
        """Parse raw Redis Lua evaluation return list."""
        raw_list: list[object] = (
            cast("list[object]", raw_result)
            if isinstance(raw_result, list)
            else list(cast("tuple[object, ...]", raw_result))
            if isinstance(raw_result, tuple)
            else []
        )
        if len(raw_list) < 3:
            logger.error("Incomplete or unexpected rate limit result from Valkey")
            return RateLimitResult(
                allowed=True, remaining_tokens=0.0, retry_after_seconds=0.0
            )

        raw_code = raw_list[0]
        allowed = bool(raw_code == 1 or raw_code == b"1" or raw_code == "1")
        tokens_val = raw_list[1]
        tokens_str = (
            tokens_val.decode("utf-8")
            if isinstance(tokens_val, (bytes, bytearray))
            else str(tokens_val)
        )
        retry_val = raw_list[2]
        retry_str = (
            retry_val.decode("utf-8")
            if isinstance(retry_val, (bytes, bytearray))
            else str(retry_val)
        )

        return RateLimitResult(
            allowed=allowed,
            remaining_tokens=max(0.0, float(tokens_str)),
            retry_after_seconds=max(0.0, float(retry_str)),
        )

    def _evaluate_in_memory(self, key: str, now: float, cost: int) -> RateLimitResult:
        """Evaluate rate limit using in-memory store."""
        if key not in self._memory_store:
            tokens = float(self._capacity)
            last_refill = now
        else:
            prev_tokens, prev_last_refill = self._memory_store[key]
            delta = max(0.0, now - prev_last_refill)
            tokens = min(
                float(self._capacity), prev_tokens + (delta * self._refill_rate)
            )
            last_refill = now

        if tokens >= cost:
            tokens -= cost
            self._memory_store[key] = (tokens, last_refill)
            return RateLimitResult(
                allowed=True,
                remaining_tokens=tokens,
                retry_after_seconds=0.0,
            )

        missing = float(cost) - tokens
        retry_after = missing / self._refill_rate if self._refill_rate > 0.0 else 0.0
        self._memory_store[key] = (tokens, last_refill)
        return RateLimitResult(
            allowed=False,
            remaining_tokens=tokens,
            retry_after_seconds=retry_after,
        )

    def reset(self, destination: str | None = None) -> None:
        """Reset in-memory rate limiter state (useful in test teardowns)."""
        if destination is None:
            self._memory_store.clear()
        else:
            key = f"{self._key_prefix}{destination}"
            self._memory_store.pop(key, None)


class RateLimitedNotificationAdapter:
    """Decorator wrapping any NotificationPort with token bucket rate limiting."""

    def __init__(
        self,
        delegate: NotificationPort,
        rate_limiter: NotificationRateLimiter,
    ) -> None:
        self._delegate = delegate
        self._rate_limiter = rate_limiter

    async def send_sms(self, to: str, message: str) -> bool:
        """Send SMS if not restricted by rate limiter."""
        res = await self._rate_limiter.check_rate_limit(to, cost=1)
        if not res.allowed:
            logger.warning(
                "SMS to %s rate-limited. Retry after %.2fs",
                to,
                res.retry_after_seconds,
            )
            return False
        return await self._delegate.send_sms(to, message)

    async def send_whatsapp(
        self,
        to: str,
        template: str,
        params: dict[str, str] | None = None,
    ) -> bool:
        """Send WhatsApp if not restricted by rate limiter."""
        res = await self._rate_limiter.check_rate_limit(to, cost=1)
        if not res.allowed:
            logger.warning(
                "WhatsApp to %s rate-limited. Retry after %.2fs",
                to,
                res.retry_after_seconds,
            )
            return False
        return await self._delegate.send_whatsapp(to, template, params)
