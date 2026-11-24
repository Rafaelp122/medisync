"""Unit tests verifying adapter resolution wiring in module composition roots."""

from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from arq.connections import ArqRedis
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authz import revocation as revocation_mod
from src.core.authz.revocation import (
    MemoryTokenRevocation,
    ValkeyTokenRevocation,
    get_token_revocation,
)
from src.core.config import CommonSettings
from src.modules.auth import composition as auth_comp
from src.modules.auth.composition import get_rate_limiter
from src.modules.auth.infrastructure.valkey_rate_limiter import (
    FakeAuthRateLimiter,
    ValkeyAuthRateLimiter,
)
from src.modules.consultation import composition as cons_comp
from src.modules.consultation.composition import (
    get_signed_cache,
    get_validation_rate_limiter,
)
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)
from src.modules.consultation.infrastructure.valkey_signed_cache import (
    ValkeySignedCache,
)
from src.modules.consultation.infrastructure.valkey_validation_rate_limiter import (
    FakeValidationRateLimiter,
    ValkeyValidationRateLimiter,
)
from src.modules.queue import composition as queue_comp
from src.modules.telemetry import composition as telemetry_comp
from src.modules.telemetry.composition import resolve_telemetry_cache
from src.modules.telemetry.infrastructure.valkey_telemetry_cache import (
    MemoryTelemetryCache,
    ValkeyTelemetryCache,
)
from src.modules.triage import composition as triage_comp
from src.modules.triage.composition import get_emergency_notifier
from src.modules.triage.infrastructure.adapters.samu_emergency_notifier_adapter import (
    SamuEmergencyNotifierAdapter,
)

from tests.doubles import FakeArqPool, FakeAsyncSession, FakeValkey


def test_auth_rate_limiter_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_comp,
        "get_settings",
        lambda: CommonSettings(RATE_LIMIT_BACKEND="memory"),
    )
    limiter = get_rate_limiter()
    assert isinstance(limiter, FakeAuthRateLimiter)

    monkeypatch.setattr(
        auth_comp,
        "get_settings",
        lambda: CommonSettings(RATE_LIMIT_BACKEND="valkey"),
    )
    limiter_valkey = get_rate_limiter()
    assert isinstance(limiter_valkey, ValkeyAuthRateLimiter)


def test_auth_token_revocation_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        revocation_mod,
        "get_settings",
        lambda: CommonSettings(TOKEN_REVOCATION_BACKEND="memory"),
    )
    revocation = get_token_revocation()
    assert isinstance(revocation, MemoryTokenRevocation)

    monkeypatch.setattr(
        revocation_mod,
        "get_settings",
        lambda: CommonSettings(TOKEN_REVOCATION_BACKEND="valkey"),
    )
    revocation_valkey = get_token_revocation()
    assert isinstance(revocation_valkey, ValkeyTokenRevocation)


def test_triage_samu_webhook_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        triage_comp,
        "get_settings",
        lambda: CommonSettings(SAMU_WEBHOOK_URL="https://samu.gov.br/webhook"),
    )
    notifier = get_emergency_notifier()
    assert isinstance(notifier, SamuEmergencyNotifierAdapter)
    assert getattr(notifier, "_webhook_url", None) == "https://samu.gov.br/webhook"


def test_consultation_validation_rate_limiter_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cons_comp,
        "get_settings",
        lambda: CommonSettings(VALIDATION_RATE_LIMIT_BACKEND="memory"),
    )
    limiter = get_validation_rate_limiter()
    assert isinstance(limiter, FakeValidationRateLimiter)

    monkeypatch.setattr(
        cons_comp,
        "get_settings",
        lambda: CommonSettings(VALIDATION_RATE_LIMIT_BACKEND="valkey"),
    )
    limiter_valkey = get_validation_rate_limiter()
    assert isinstance(limiter_valkey, ValkeyValidationRateLimiter)


def test_consultation_signed_cache_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        get_signed_cache.cache_clear()
        monkeypatch.setattr(
            cons_comp,
            "get_settings",
            lambda: CommonSettings(SIGNED_CACHE_BACKEND="memory"),
        )
        cache_mem = get_signed_cache()
        assert isinstance(cache_mem, MemorySignedCache)

        get_signed_cache.cache_clear()
        monkeypatch.setattr(
            cons_comp,
            "get_settings",
            lambda: CommonSettings(SIGNED_CACHE_BACKEND="valkey"),
        )
        cache_valkey = get_signed_cache()
        assert isinstance(cache_valkey, ValkeySignedCache)
    finally:
        get_signed_cache.cache_clear()


def test_telemetry_cache_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        telemetry_comp,
        "get_settings",
        lambda: CommonSettings(TELEMETRY_CACHE_BACKEND="memory"),
    )
    cache = resolve_telemetry_cache()
    assert isinstance(cache, MemoryTelemetryCache)

    monkeypatch.setattr(
        telemetry_comp,
        "get_settings",
        lambda: CommonSettings(TELEMETRY_CACHE_BACKEND="valkey"),
    )
    cache_valkey = resolve_telemetry_cache()
    assert isinstance(cache_valkey, ValkeyTelemetryCache)


def test_ambulatory_service_resolution() -> None:
    from src.modules.ambulatory.composition import build_elegibilidade_service
    from src.modules.ambulatory.infrastructure.adapters.sus_adapter import (
        SusEligibilityAdapter,
    )

    sus_service = build_elegibilidade_service()
    assert isinstance(
        sus_service._provider,  # pyright: ignore[reportPrivateUsage]
        SusEligibilityAdapter,
    )


def test_ambulatory_producao_service_builder() -> None:
    from src.modules.ambulatory.application.services.producao_service import (
        ProducaoAmbulatorialService,
    )
    from src.modules.ambulatory.composition import (
        build_producao_ambulatorial_service,
        get_producao_ambulatorial_service,
    )

    fake_session = cast("AsyncSession", FakeAsyncSession())
    service = build_producao_ambulatorial_service(session=fake_session)
    assert isinstance(service, ProducaoAmbulatorialService)
    assert service._session is fake_session  # pyright: ignore[reportPrivateUsage]

    dep_service = get_producao_ambulatorial_service(session=fake_session)
    assert isinstance(dep_service, ProducaoAmbulatorialService)
    assert dep_service._session is fake_session  # pyright: ignore[reportPrivateUsage]


def test_queue_alocacao_wiring_with_arq() -> None:
    from src.modules.queue.composition import build_alocacao_service_for_session

    fake_valkey = cast("Redis", FakeValkey())
    fake_session = cast("AsyncSession", FakeAsyncSession())
    fake_arq = cast("ArqRedis", FakeArqPool())

    service = build_alocacao_service_for_session(
        valkey=fake_valkey, session=fake_session, arq_pool=fake_arq
    )
    assert service._arq_pool is fake_arq  # pyright: ignore[reportPrivateUsage]


def test_queue_notification_rate_limiter_settings_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.modules.queue.composition import get_notification_rate_limiter
    from src.modules.queue.infrastructure.notifications import (
        NotificationRateLimiter,
    )

    fake_valkey = cast("Redis", FakeValkey())
    monkeypatch.setattr(
        queue_comp,
        "get_settings",
        lambda: CommonSettings(
            NOTIFICATION_RATE_LIMIT_CAPACITY=8,
            NOTIFICATION_RATE_LIMIT_REFILL_RATE=0.25,
            NOTIFICATION_RATE_LIMIT_TTL_SECONDS=7200,
        ),
    )
    limiter = get_notification_rate_limiter(valkey=fake_valkey)
    assert isinstance(limiter, NotificationRateLimiter)
    assert limiter._capacity == 8  # pyright: ignore[reportPrivateUsage]
    assert limiter._refill_rate == 0.25  # pyright: ignore[reportPrivateUsage]
    assert limiter._ttl_seconds == 7200  # pyright: ignore[reportPrivateUsage]
    assert limiter._valkey is fake_valkey  # pyright: ignore[reportPrivateUsage]


def test_queue_notification_adapter_resolution_with_rate_limiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.modules.queue.composition import get_notification_adapter
    from src.modules.queue.infrastructure.notifications import (
        LoggingNotificationAdapter,
        RateLimitedNotificationAdapter,
    )

    fake_valkey = cast("Redis", FakeValkey())
    monkeypatch.setattr(
        queue_comp,
        "get_settings",
        lambda: CommonSettings(
            NOTIFICATION_PROVIDER="console",
            NOTIFICATION_RATE_LIMIT_CAPACITY=10,
        ),
    )
    adapter = get_notification_adapter(valkey=fake_valkey)
    assert isinstance(adapter, RateLimitedNotificationAdapter)
    assert isinstance(
        adapter._delegate,  # pyright: ignore[reportPrivateUsage]
        LoggingNotificationAdapter,
    )
    assert (
        adapter._rate_limiter._capacity  # pyright: ignore[reportPrivateUsage]
        == 10
    )


def test_queue_notification_adapter_noop_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.modules.queue.composition import get_notification_adapter

    fake_valkey = cast("Redis", FakeValkey())
    monkeypatch.setattr(
        queue_comp,
        "get_settings",
        lambda: CommonSettings(NOTIFICATION_PROVIDER="noop"),
    )
    adapter = get_notification_adapter(valkey=fake_valkey)
    assert adapter is None


def test_queue_alocacao_service_build_wiring_with_valkey() -> None:
    from src.modules.consultation.application.realtime_channels import (
        channel_doctor_calls,
    )
    from src.modules.queue.composition import build_alocacao_service_for_session
    from src.modules.queue.infrastructure.notifications import (
        RateLimitedNotificationAdapter,
    )
    from src.modules.queue.infrastructure.valkey_queue_engine import ValkeyQueueEngine

    fake_valkey = cast("Redis", FakeValkey())
    fake_session = cast("AsyncSession", FakeAsyncSession())

    service = build_alocacao_service_for_session(
        valkey=fake_valkey, session=fake_session
    )
    assert isinstance(
        service._notification_adapter,  # pyright: ignore[reportPrivateUsage]
        RateLimitedNotificationAdapter,
    )
    assert (
        service._notification_adapter._rate_limiter._valkey  # pyright: ignore[reportPrivateUsage]
        is fake_valkey
    )
    assert isinstance(
        service._queue_engine,  # pyright: ignore[reportPrivateUsage]
        ValkeyQueueEngine,
    )
    assert (
        service._queue_engine._doctor_channel_fn  # pyright: ignore[reportPrivateUsage]
        is channel_doctor_calls
    )


def test_queue_notification_rate_limiter_in_memory_fallback() -> None:
    from src.modules.queue.composition import get_notification_adapter
    from src.modules.queue.infrastructure.notifications import (
        RateLimitedNotificationAdapter,
    )

    adapter = get_notification_adapter(valkey=None)
    assert isinstance(adapter, RateLimitedNotificationAdapter)
    assert (
        adapter._rate_limiter._valkey  # pyright: ignore[reportPrivateUsage]
        is None
    )


def test_auth_and_identity_session_factories() -> None:
    from src.modules.auth.composition import build_auth_service_for_session
    from src.modules.identity.composition import (
        build_dependente_service_for_session,
        build_onboarding_service_for_session,
    )

    fake_session = cast("AsyncSession", FakeAsyncSession())
    auth_srv = build_auth_service_for_session(session=fake_session)
    assert auth_srv._session is fake_session  # pyright: ignore[reportPrivateUsage]

    onb_srv = build_onboarding_service_for_session(session=fake_session)
    assert onb_srv._session is fake_session  # pyright: ignore[reportPrivateUsage]

    dep_srv = build_dependente_service_for_session(session=fake_session)
    assert dep_srv._session is fake_session  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_valkey_queue_engine_publicar_evento_medico_dispatches_event() -> None:
    import json
    from typing import cast
    from uuid import uuid4

    from src.modules.consultation.application.realtime_channels import (
        channel_doctor_calls,
    )
    from src.modules.queue.composition import build_queue_engine

    from tests.doubles import FakeValkey

    fake_valkey = FakeValkey()
    engine = build_queue_engine(valkey=cast("Redis", fake_valkey))
    med_id = uuid4()
    atend_id = uuid4()

    pubsub = fake_valkey.pubsub()
    await pubsub.subscribe(channel_doctor_calls(med_id))

    await engine.publicar_evento_medico(
        med_id,
        {
            "event": "INCOMING_CALL",
            "atendimento_id": str(atend_id),
            "medico_id": str(med_id),
            "ttl_segundos": 45,
            "chamada_iniciada_em": "2026-10-18T00:00:00Z",
        },
    )

    received: dict[str, object] = {}
    async for msg in pubsub.listen():
        received = json.loads(str(msg["data"]))
        break

    assert received["event"] == "INCOMING_CALL"
    assert received["atendimento_id"] == str(atend_id)
    assert received["medico_id"] == str(med_id)
