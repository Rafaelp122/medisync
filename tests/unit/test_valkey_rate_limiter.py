"""Unit tests for anti-brute force rate limiter adapters."""

import pytest
from src.modules.auth.application.ports.auth_rate_limiter_port import (
    AuthRateLimiterPort,
)
from src.modules.auth.infrastructure.valkey_rate_limiter import (
    FakeAuthRateLimiter,
)


def test_rate_limiter_conformance() -> None:
    """Validate that FakeAuthRateLimiter satisfies AuthRateLimiterPort."""
    limiter = FakeAuthRateLimiter()
    assert isinstance(limiter, AuthRateLimiterPort)


@pytest.mark.asyncio
async def test_fake_rate_limiter_threshold_and_lockout() -> None:
    """Validate that rate limiter permits up to threshold then locks out with retry."""
    limiter = FakeAuthRateLimiter()
    key = "ip:192.168.1.10"
    max_attempts = 3
    window = 60

    # 1. First attempt allowed
    res1 = await limiter.verificar_e_incrementar(
        key, limite=max_attempts, janela_segundos=window
    )
    assert res1.permitido is True
    assert res1.tentativas_restantes == 2

    # 2. Second attempt allowed
    res2 = await limiter.verificar_e_incrementar(
        key, limite=max_attempts, janela_segundos=window
    )
    assert res2.permitido is True
    assert res2.tentativas_restantes == 1

    # 3. Third attempt allowed
    res3 = await limiter.verificar_e_incrementar(
        key, limite=max_attempts, janela_segundos=window
    )
    assert res3.permitido is True
    assert res3.tentativas_restantes == 0

    # 4. Fourth attempt blocked
    res4 = await limiter.verificar_e_incrementar(
        key, limite=max_attempts, janela_segundos=window
    )
    assert res4.permitido is False
    assert res4.tentativas_restantes == 0
    assert res4.retry_after_segundos > 0

    # 5. Reset restores access
    await limiter.resetar(key)
    res5 = await limiter.verificar_e_incrementar(
        key, limite=max_attempts, janela_segundos=window
    )
    assert res5.permitido is True
    assert res5.tentativas_restantes == 2
