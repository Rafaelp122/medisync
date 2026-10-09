"""Unit tests for composition providers (DI Fase 3 without infra defaults)."""

from collections.abc import Generator
from typing import cast
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import Settings


@pytest.fixture(autouse=True)
def _clear_composition_cache() -> Generator[None, None, None]:
    from src.modules.consultation import composition

    composition.get_storage.cache_clear()
    composition.get_signed_cache.cache_clear()
    yield
    composition.get_storage.cache_clear()
    composition.get_signed_cache.cache_clear()


def test_lua_script_manager_satisfies_lua_script_port() -> None:
    """LuaScriptManager must structurally satisfy the application port."""
    from src.modules.queue.application.ports.lua_script_port import LuaScriptPort
    from src.modules.queue.infrastructure.lua_loader import LuaScriptManager

    manager = LuaScriptManager()
    assert isinstance(manager, LuaScriptPort)


def test_get_storage_returns_fake_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STORAGE_BACKEND=fake must resolve to FakeStorageAdapter."""
    from src.modules.consultation import composition
    from src.modules.consultation.infrastructure.s3_storage import FakeStorageAdapter

    monkeypatch.setattr(
        composition,
        "get_settings",
        lambda: Settings(STORAGE_BACKEND="fake"),
    )
    storage = composition.get_storage()
    assert isinstance(storage, FakeStorageAdapter)


def test_get_storage_returns_s3_with_injected_client_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STORAGE_BACKEND=s3 must resolve to S3StorageAdapter with settings vars."""
    from src.modules.consultation import composition
    from src.modules.consultation.infrastructure.s3_storage import S3StorageAdapter

    monkeypatch.setattr(
        composition,
        "get_settings",
        lambda: Settings(
            STORAGE_BACKEND="s3",
            S3_ENDPOINT_URL="http://s3-test:9000",
            S3_BUCKET_NAME="test-bucket",
            S3_ACCESS_KEY_ID="test-key",
            S3_SECRET_ACCESS_KEY="test-secret",
            S3_REGION_NAME="us-east-1",
        ),
    )
    storage = composition.get_storage()
    assert isinstance(storage, S3StorageAdapter)
    assert storage._endpoint_url == "http://s3-test:9000"  # pyright: ignore[reportPrivateUsage]
    assert storage._bucket_name == "test-bucket"  # pyright: ignore[reportPrivateUsage]


def test_get_auth_service_wires_real_adapters() -> None:
    """Auth composition must wire hasher, token service and rate limiter."""
    from src.modules.auth.composition import get_auth_service
    from src.modules.auth.infrastructure.argon2_hasher import Argon2PasswordHasher
    from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
    from src.modules.auth.infrastructure.valkey_rate_limiter import (
        ValkeyAuthRateLimiter,
    )

    session = AsyncMock(spec=AsyncSession)
    service = get_auth_service(cast("AsyncSession", session))
    assert isinstance(service._hasher, Argon2PasswordHasher)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(service._token_service, JWTTokenService)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(service._rate_limiter, ValkeyAuthRateLimiter)  # pyright: ignore[reportPrivateUsage]


def test_get_pep_service_wires_real_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PEP composition must wire pdf generator, signer and fake storage."""
    from src.modules.consultation import composition
    from src.modules.consultation.infrastructure.pdf_generator import (
        ReportLabPDFGenerator,
    )
    from src.modules.consultation.infrastructure.pyhanko_signer import PyHankoSigner
    from src.modules.consultation.infrastructure.s3_storage import FakeStorageAdapter

    monkeypatch.setattr(
        composition,
        "get_settings",
        lambda: Settings(STORAGE_BACKEND="fake"),
    )
    session = AsyncMock(spec=AsyncSession)
    service = composition.get_pep_service(cast("AsyncSession", session))
    assert isinstance(service._pdf_generator, ReportLabPDFGenerator)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(service._signer, PyHankoSigner)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(service._storage, FakeStorageAdapter)  # pyright: ignore[reportPrivateUsage]


def test_get_alocacao_service_injects_lua_port() -> None:
    """Queue composition must inject a LuaScriptPort-compliant manager."""
    from src.modules.queue.application.ports.lua_script_port import LuaScriptPort
    from src.modules.queue.composition import get_alocacao_service

    valkey = cast("Redis", AsyncMock(spec=Redis))
    session = AsyncMock(spec=AsyncSession)
    service = get_alocacao_service(valkey, cast("AsyncSession", session))
    assert isinstance(service._lua_manager, LuaScriptPort)  # pyright: ignore[reportPrivateUsage]


def test_get_livekit_adapter_from_composition() -> None:
    """LiveKit adapter factory must live in consultation composition."""
    from src.modules.consultation.composition import get_livekit_adapter
    from src.modules.consultation.infrastructure.livekit_adapter import LiveKitAdapter

    adapter = get_livekit_adapter()
    assert isinstance(adapter, LiveKitAdapter)


def test_get_onboarding_and_dependente_services() -> None:
    """Identity composition must provide service instances."""
    from unittest.mock import AsyncMock

    from src.modules.identity.application.services.dependente_service import (
        DependenteService,
    )
    from src.modules.identity.application.services.onboarding_service import (
        OnboardingService,
    )
    from src.modules.identity.composition import (
        get_dependente_service,
        get_onboarding_service,
    )

    mock_session = AsyncMock()
    assert isinstance(get_onboarding_service(session=mock_session), OnboardingService)
    assert isinstance(get_dependente_service(session=mock_session), DependenteService)
