"""Unit tests verifying adapter resolution wiring in module composition roots."""

from unittest.mock import patch

from src.core.config import CommonSettings
from src.modules.auth.composition import get_rate_limiter, get_token_revocation
from src.modules.auth.infrastructure.valkey_rate_limiter import (
    FakeAuthRateLimiter,
    ValkeyAuthRateLimiter,
)
from src.modules.auth.infrastructure.valkey_token_revocation import (
    MemoryTokenRevocation,
    ValkeyTokenRevocation,
)
from src.modules.consultation.composition import get_validation_rate_limiter
from src.modules.consultation.infrastructure.valkey_validation_rate_limiter import (
    FakeValidationRateLimiter,
    ValkeyValidationRateLimiter,
)
from src.modules.telemetry.composition import resolve_telemetry_cache
from src.modules.telemetry.infrastructure.valkey_telemetry_cache import (
    MemoryTelemetryCache,
    ValkeyTelemetryCache,
)
from src.modules.triage.composition import get_emergency_notifier
from src.modules.triage.infrastructure.adapters.samu_emergency_notifier_adapter import (
    SamuEmergencyNotifierAdapter,
)


def test_auth_rate_limiter_resolution() -> None:
    with patch("src.modules.auth.composition.get_settings") as mock_settings:
        mock_settings.return_value = CommonSettings(RATE_LIMIT_BACKEND="memory")
        limiter = get_rate_limiter()
        assert isinstance(limiter, FakeAuthRateLimiter)

        mock_settings.return_value = CommonSettings(RATE_LIMIT_BACKEND="valkey")
        limiter_valkey = get_rate_limiter()
        assert isinstance(limiter_valkey, ValkeyAuthRateLimiter)


def test_auth_token_revocation_resolution() -> None:
    with patch("src.modules.auth.composition.get_settings") as mock_settings:
        mock_settings.return_value = CommonSettings(TOKEN_REVOCATION_BACKEND="memory")
        revocation = get_token_revocation()
        assert isinstance(revocation, MemoryTokenRevocation)

        mock_settings.return_value = CommonSettings(TOKEN_REVOCATION_BACKEND="valkey")
        revocation_valkey = get_token_revocation()
        assert isinstance(revocation_valkey, ValkeyTokenRevocation)


def test_triage_samu_webhook_wiring() -> None:
    with patch("src.modules.triage.composition.get_settings") as mock_settings:
        mock_settings.return_value = CommonSettings(
            SAMU_WEBHOOK_URL="https://samu.gov.br/webhook"
        )
        notifier = get_emergency_notifier()
        assert isinstance(notifier, SamuEmergencyNotifierAdapter)
        assert getattr(notifier, "_webhook_url", None) == "https://samu.gov.br/webhook"


def test_consultation_validation_rate_limiter_resolution() -> None:
    with patch("src.modules.consultation.composition.get_settings") as mock_settings:
        mock_settings.return_value = CommonSettings(
            VALIDATION_RATE_LIMIT_BACKEND="memory"
        )
        limiter = get_validation_rate_limiter()
        assert isinstance(limiter, FakeValidationRateLimiter)

        mock_settings.return_value = CommonSettings(
            VALIDATION_RATE_LIMIT_BACKEND="valkey"
        )
        limiter_valkey = get_validation_rate_limiter()
        assert isinstance(limiter_valkey, ValkeyValidationRateLimiter)


def test_telemetry_cache_resolution() -> None:
    with patch("src.modules.telemetry.composition.get_settings") as mock_settings:
        mock_settings.return_value = CommonSettings(TELEMETRY_CACHE_BACKEND="memory")
        cache = resolve_telemetry_cache()
        assert isinstance(cache, MemoryTelemetryCache)

        mock_settings.return_value = CommonSettings(TELEMETRY_CACHE_BACKEND="valkey")
        cache_valkey = resolve_telemetry_cache()
        assert isinstance(cache_valkey, ValkeyTelemetryCache)


def test_billing_service_resolution() -> None:
    from src.modules.billing.composition import build_elegibilidade_service
    from src.modules.billing.infrastructure.adapters.private_gateway_adapter import (
        PrivateInsuranceGatewayAdapter,
    )
    from src.modules.billing.infrastructure.adapters.sus_adapter import (
        SusEligibilityAdapter,
    )

    sus_service = build_elegibilidade_service(is_sus=True)
    assert isinstance(
        sus_service._provider,  # pyright: ignore[reportPrivateUsage]
        SusEligibilityAdapter,
    )

    private_service = build_elegibilidade_service(is_sus=False)
    assert isinstance(
        private_service._provider,  # pyright: ignore[reportPrivateUsage]
        PrivateInsuranceGatewayAdapter,
    )


def test_queue_alocacao_wiring_with_arq() -> None:
    from unittest.mock import AsyncMock

    from src.modules.queue.composition import build_alocacao_service_for_session

    mock_valkey = AsyncMock()
    mock_session = AsyncMock()
    mock_arq = AsyncMock()

    service = build_alocacao_service_for_session(
        valkey=mock_valkey, session=mock_session, arq_pool=mock_arq
    )
    assert service._arq_pool is mock_arq  # pyright: ignore[reportPrivateUsage]


def test_auth_and_identity_session_factories() -> None:
    from unittest.mock import AsyncMock

    from src.modules.auth.composition import build_auth_service_for_session
    from src.modules.identity.composition import (
        build_dependente_service_for_session,
        build_onboarding_service_for_session,
    )

    mock_session = AsyncMock()
    auth_srv = build_auth_service_for_session(session=mock_session)
    assert auth_srv._session is mock_session  # pyright: ignore[reportPrivateUsage]

    onb_srv = build_onboarding_service_for_session(session=mock_session)
    assert onb_srv._session is mock_session  # pyright: ignore[reportPrivateUsage]

    dep_srv = build_dependente_service_for_session(session=mock_session)
    assert dep_srv._session is mock_session  # pyright: ignore[reportPrivateUsage]
