"""Unit tests for notification ports, adapters, and rate limiting."""

import asyncio

import pytest
from src.core.notifications import (
    ConsoleNotificationAdapter,
    FakeNotificationAdapter,
    LoggingNotificationAdapter,
    NotificationPort,
    NotificationRateLimiter,
    RateLimitedNotificationAdapter,
)


def test_logging_notification_adapter_protocol_compliance() -> None:
    """Validate that LoggingNotificationAdapter conforms to NotificationPort."""
    adapter = LoggingNotificationAdapter()
    assert isinstance(adapter, NotificationPort)
    assert isinstance(ConsoleNotificationAdapter(), NotificationPort)
    assert isinstance(FakeNotificationAdapter(), NotificationPort)


@pytest.mark.asyncio
async def test_logging_notification_adapter_send_sms() -> None:
    """Verify that send_sms logs, stores in-memory, and returns True."""
    adapter = LoggingNotificationAdapter()
    phone = "+5511999998888"
    msg = "Seu código de acesso é 123456"

    result = await adapter.send_sms(phone, msg)

    assert result is True
    assert len(adapter.sent_sms) == 1
    assert adapter.sent_sms[0]["to"] == phone
    assert adapter.sent_sms[0]["message"] == msg


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
    """Verify that clear() empties recorded messages."""
    adapter = LoggingNotificationAdapter()
    adapter.sent_sms.append({"to": "123", "message": "test"})
    adapter.sent_whatsapp.append({"to": "123", "template": "test", "params": {}})

    adapter.clear()

    assert len(adapter.sent_sms) == 0
    assert len(adapter.sent_whatsapp) == 0


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_burst_and_rejection() -> None:
    """Validate token bucket burst consumption and subsequent rejection."""
    limiter = NotificationRateLimiter(
        valkey_client=None,
        capacity=3,
        refill_rate_per_second=0.1,  # 1 token every 10 seconds
    )
    phone = "+5511977776666"

    # 1. First 3 requests should be allowed
    r1 = await limiter.check_rate_limit(phone, cost=1)
    assert r1.allowed is True
    assert pytest.approx(r1.remaining_tokens, abs=0.05) == 2.0

    r2 = await limiter.check_rate_limit(phone, cost=1)
    assert r2.allowed is True
    assert pytest.approx(r2.remaining_tokens, abs=0.05) == 1.0

    r3 = await limiter.check_rate_limit(phone, cost=1)
    assert r3.allowed is True
    assert pytest.approx(r3.remaining_tokens, abs=0.05) == 0.0

    # 2. 4th request should be rejected (rate limited)
    r4 = await limiter.check_rate_limit(phone, cost=1)
    assert r4.allowed is False
    assert pytest.approx(r4.remaining_tokens, abs=0.05) == 0.0
    assert r4.retry_after_seconds > 0.0

    # 3. acquire helper should return False
    allowed = await limiter.acquire(phone, cost=1)
    assert allowed is False


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_token_refill() -> None:
    """Validate that tokens refill over elapsed time."""
    limiter = NotificationRateLimiter(
        valkey_client=None,
        capacity=2,
        refill_rate_per_second=10.0,  # 10 tokens per second (fast refill for testing)
    )
    phone = "+5511966665555"

    # Consume all tokens
    await limiter.acquire(phone, cost=1)
    await limiter.acquire(phone, cost=1)

    # Immediate next request should fail
    assert await limiter.acquire(phone, cost=1) is False

    # Sleep 0.15s to replenish at least 1.5 tokens
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

    # 1. First SMS passes
    sms_res = await adapter.send_sms(phone, "Mensagem 1")
    assert sms_res is True
    assert len(fake_delegate.sent_sms) == 1

    # 2. Second SMS immediately fails due to rate limit
    sms_res2 = await adapter.send_sms(phone, "Mensagem 2")
    assert sms_res2 is False
    assert len(fake_delegate.sent_sms) == 1  # Not sent to delegate

    # 3. WhatsApp on different phone number passes
    other_phone = "+5511911112222"
    wa_res = await adapter.send_whatsapp(other_phone, "template_a")
    assert wa_res is True
    assert len(fake_delegate.sent_whatsapp) == 1

    # 4. WhatsApp on exhausted phone number is rate limited
    wa_res2 = await adapter.send_whatsapp(phone, "template_b")
    assert wa_res2 is False
    assert len(fake_delegate.sent_whatsapp) == 1
