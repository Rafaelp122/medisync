"""Integration tests for Valkey 8.0 atomic token bucket rate limiter."""

import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from src.core.notifications import NotificationRateLimiter
from src.core.valkey import close_valkey_pool, get_valkey_pool


@pytest.fixture(autouse=True)
async def cleanup_valkey() -> AsyncGenerator[None]:
    """Ensure pool is gracefully closed after tests."""
    yield
    await close_valkey_pool()


@pytest.mark.asyncio
async def test_valkey_rate_limiter_burst_and_rejection() -> None:
    """Verify live atomic rate limiting in Valkey 8.0 with token bucket."""
    pool = get_valkey_pool()
    client = Redis(connection_pool=pool)

    test_phone = f"+55119{uuid4().hex[:8]}"
    limiter = NotificationRateLimiter(
        valkey_client=client,
        capacity=3,
        refill_rate_per_second=0.01,  # 1 token every 100 seconds
        ttl_seconds=60,
        key_prefix="test:ratelimit:",
    )

    try:
        # 1. First 3 requests must be allowed
        r1 = await limiter.check_rate_limit(test_phone, cost=1)
        assert r1.allowed is True
        assert pytest.approx(r1.remaining_tokens, abs=0.05) == 2.0

        r2 = await limiter.check_rate_limit(test_phone, cost=1)
        assert r2.allowed is True
        assert pytest.approx(r2.remaining_tokens, abs=0.05) == 1.0

        r3 = await limiter.check_rate_limit(test_phone, cost=1)
        assert r3.allowed is True
        assert pytest.approx(r3.remaining_tokens, abs=0.05) == 0.0

        # 2. 4th request must be rejected (rate limited)
        r4 = await limiter.check_rate_limit(test_phone, cost=1)
        assert r4.allowed is False
        assert pytest.approx(r4.remaining_tokens, abs=0.05) == 0.0
        assert r4.retry_after_seconds > 0.0

        # 3. Key in Valkey must have positive TTL
        ttl = await client.ttl(f"test:ratelimit:{test_phone}")
        assert ttl > 0
    finally:
        await client.delete(f"test:ratelimit:{test_phone}")


@pytest.mark.asyncio
async def test_valkey_rate_limiter_atomic_concurrency() -> None:
    """Verify zero race conditions under concurrent burst against the same phone."""
    pool = get_valkey_pool()
    client = Redis(connection_pool=pool)

    test_phone = f"+55119{uuid4().hex[:8]}"
    capacity = 5
    limiter = NotificationRateLimiter(
        valkey_client=client,
        capacity=capacity,
        refill_rate_per_second=0.001,
        ttl_seconds=60,
        key_prefix="test:ratelimit:",
    )

    try:
        # 20 concurrent requests at the exact same millisecond
        async def make_request() -> bool:
            return await limiter.acquire(test_phone, cost=1)

        tasks = [asyncio.create_task(make_request()) for _ in range(20)]
        results = await asyncio.gather(*tasks)

        allowed_count = sum(1 for r in results if r is True)
        rejected_count = sum(1 for r in results if r is False)

        # Strictly exactly 5 must succeed and 15 must be rejected
        assert allowed_count == capacity
        assert rejected_count == 15
    finally:
        await client.delete(f"test:ratelimit:{test_phone}")
