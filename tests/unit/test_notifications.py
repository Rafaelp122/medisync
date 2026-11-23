"""Unit tests for WhatsApp notification ports, adapters, and rate limiting."""

import asyncio

import pytest
from src.modules.queue.application.ports.notification_port import NotificationPort
from src.modules.queue.infrastructure.notifications import (
    LoggingNotificationAdapter,
    NotificationRateLimiter,
    RateLimitedNotificationAdapter,
)


def test_logging_notification_adapter_protocol_compliance() -> None:
    """Validate that LoggingNotificationAdapter conforms to NotificationPort."""
    adapter = LoggingNotificationAdapter()
    assert isinstance(adapter, NotificationPort)


@pytest.mark.asyncio
async def test_logging_notification_adapter_send_whatsapp() -> None:
    """Verify that send_whatsapp logs, stores in-memory, and returns True."""
    adapter = LoggingNotificationAdapter()
    phone = "+5511988887777"
    template = "chamada_consulta"
    params = {"medico": "Dr. Silva", "sala": "Consultório 3"}

    result = await adapter.send_whatsapp(phone, template, params)

    assert result is True
    assert len(adapter.sent_whatsapp) == 1
    assert adapter.sent_whatsapp[0]["to"] == phone
    assert adapter.sent_whatsapp[0]["template"] == template
    assert adapter.sent_whatsapp[0]["params"] == params


def test_logging_notification_adapter_clear() -> None:
    """Verify that clear() empties recorded WhatsApp messages."""
    adapter = LoggingNotificationAdapter()
    adapter.sent_whatsapp.append({"to": "123", "template": "test", "params": {}})

    adapter.clear()

    assert len(adapter.sent_whatsapp) == 0


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_burst_and_rejection() -> None:
    """Validate token bucket burst consumption and subsequent rejection."""
    limiter = NotificationRateLimiter(
        valkey_client=None,
        capacity=3,
        refill_rate_per_second=0.1,
    )
    phone = "+5511977776666"

    r1 = await limiter.check_rate_limit(phone, cost=1)
    assert r1.allowed is True
    assert pytest.approx(r1.remaining_tokens, abs=0.05) == 2.0

    r2 = await limiter.check_rate_limit(phone, cost=1)
    assert r2.allowed is True
    assert pytest.approx(r2.remaining_tokens, abs=0.05) == 1.0

    r3 = await limiter.check_rate_limit(phone, cost=1)
    assert r3.allowed is True
    assert pytest.approx(r3.remaining_tokens, abs=0.05) == 0.0

    r4 = await limiter.check_rate_limit(phone, cost=1)
    assert r4.allowed is False
    assert pytest.approx(r4.remaining_tokens, abs=0.05) == 0.0
    assert r4.retry_after_seconds > 0.0

    allowed = await limiter.acquire(phone, cost=1)
    assert allowed is False


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_token_refill() -> None:
    """Validate that tokens refill over elapsed time."""
    limiter = NotificationRateLimiter(
        valkey_client=None,
        capacity=2,
        refill_rate_per_second=10.0,
    )
    phone = "+5511966665555"

    await limiter.acquire(phone, cost=1)
    await limiter.acquire(phone, cost=1)
    assert await limiter.acquire(phone, cost=1) is False

    await asyncio.sleep(0.15)
    res = await limiter.check_rate_limit(phone, cost=1)
    assert res.allowed is True


@pytest.mark.asyncio
async def test_rate_limited_adapter_delegation_and_blocking() -> None:
    """Validate RateLimitedNotificationAdapter behavior with delegate."""
    fake_delegate = LoggingNotificationAdapter()
    limiter = NotificationRateLimiter(
        valkey_client=None,
        capacity=1,
        refill_rate_per_second=0.01,
    )
    adapter = RateLimitedNotificationAdapter(
        delegate=fake_delegate,
        rate_limiter=limiter,
    )
    phone = "+5511955554444"
    other_phone = "+5511911112222"

    wa_res1 = await adapter.send_whatsapp(phone, "chamada_consulta")
    assert wa_res1 is True
    assert len(fake_delegate.sent_whatsapp) == 1

    wa_res2 = await adapter.send_whatsapp(phone, "chamada_consulta")
    assert wa_res2 is False
    assert len(fake_delegate.sent_whatsapp) == 1

    wa_res3 = await adapter.send_whatsapp(other_phone, "template_a")
    assert wa_res3 is True
    assert len(fake_delegate.sent_whatsapp) == 2
