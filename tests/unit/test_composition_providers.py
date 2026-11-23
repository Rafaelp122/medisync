"""Unit tests for composition providers (DI Fase 3 without infra defaults)."""

from collections.abc import Generator
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import Settings

if TYPE_CHECKING:
    from redis.asyncio import Redis


@pytest.fixture(autouse=True)
def _clear_composition_cache() -> Generator[None, None, None]:
    from src.modules.consultation import composition

    composition.get_storage.cache_clear()
    composition.get_signed_cache.cache_clear()
    yield
    composition.get_storage.cache_clear()
    composition.get_signed_cache.cache_clear()


def test_valkey_queue_engine_satisfies_queue_engine_port() -> None:
    """ValkeyQueueEngine must structurally satisfy QueueEnginePort."""
    from src.modules.queue.application.ports.queue_engine_port import QueueEnginePort
    from src.modules.queue.infrastructure.valkey_queue_engine import ValkeyQueueEngine

    from tests.doubles import FakeValkey

    engine = ValkeyQueueEngine(valkey=cast("Redis", FakeValkey()))
    assert isinstance(engine, QueueEnginePort)


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


def test_get_auth_service_wires_real_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auth composition must wire hasher, token service and rate limiter."""
    from src.core.config import get_settings
    from src.modules.auth.composition import get_auth_service
    from src.modules.auth.infrastructure.argon2_hasher import Argon2PasswordHasher
    from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
    from src.modules.auth.infrastructure.valkey_rate_limiter import (
        ValkeyAuthRateLimiter,
    )

    monkeypatch.setenv("ENVIRONMENT", "development")
    get_settings.cache_clear()
    session = AsyncMock(spec=AsyncSession)
    service = get_auth_service(cast("AsyncSession", session))
    assert isinstance(service._hasher, Argon2PasswordHasher)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(service._token_service, JWTTokenService)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(service._rate_limiter, ValkeyAuthRateLimiter)  # pyright: ignore[reportPrivateUsage]


def test_get_pep_service_wires_real_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PEP composition must wire ClinicalPdfCompiler and FakeStorage without Signer."""
    from src.modules.consultation import composition
    from src.modules.consultation.application.services.clinical_pdf_compiler import (
        ClinicalPdfCompiler,
    )
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
    assert isinstance(service._pdf_compiler, ClinicalPdfCompiler)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(service._pdf_compiler._pdf_generator, ReportLabPDFGenerator)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(service._pdf_compiler._storage, FakeStorageAdapter)  # pyright: ignore[reportPrivateUsage]
    assert not hasattr(service, "_signer")
    assert not hasattr(service, "_pdf_generator")

    built = composition.build_pep_service_for_session(cast("AsyncSession", session))
    assert isinstance(built._pdf_compiler, ClinicalPdfCompiler)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(built._pdf_compiler._pdf_generator, ReportLabPDFGenerator)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(built._pdf_compiler._storage, FakeStorageAdapter)  # pyright: ignore[reportPrivateUsage]

    doc_service = composition.get_documento_service(cast("AsyncSession", session))
    assert isinstance(doc_service._signer, PyHankoSigner)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(doc_service._pdf_compiler, ClinicalPdfCompiler)  # pyright: ignore[reportPrivateUsage]

    val_service = composition.get_document_validation_service(
        cast("AsyncSession", session)
    )
    assert isinstance(val_service._storage, FakeStorageAdapter)  # pyright: ignore[reportPrivateUsage]
    assert val_service._compilador_pdf.__self__ is not doc_service  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]


def test_build_fila_service_injects_queue_engine_and_shift_policy() -> None:
    """Queue composition must inject QueueEnginePort and ShiftPolicyReaderPort."""
    from src.modules.queue.application.ports.queue_engine_port import QueueEnginePort
    from src.modules.queue.application.ports.shift_policy_reader_port import (
        ShiftPolicyReaderPort,
    )
    from src.modules.queue.composition import build_fila_service_for_session

    from tests.doubles import FakeAsyncSession, FakeValkey

    valkey = cast("Redis", FakeValkey())
    session = cast("AsyncSession", FakeAsyncSession())
    service = build_fila_service_for_session(session=session, valkey=valkey)
    assert isinstance(service._queue_engine, QueueEnginePort)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(
        service._shift_policy_reader,  # pyright: ignore[reportPrivateUsage]
        ShiftPolicyReaderPort,
    )


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


def test_get_signed_cache_returns_memory_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SIGNED_CACHE_BACKEND=memory must resolve to MemorySignedCache."""
    from src.modules.consultation import composition
    from src.modules.consultation.infrastructure.memory_signed_cache import (
        MemorySignedCache,
    )

    monkeypatch.setattr(
        composition,
        "get_settings",
        lambda: Settings(SIGNED_CACHE_BACKEND="memory"),
    )
    cache = composition.get_signed_cache()
    assert isinstance(cache, MemorySignedCache)


def test_get_signed_cache_returns_valkey_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SIGNED_CACHE_BACKEND=valkey must resolve to ValkeySignedCache."""
    from src.modules.consultation import composition
    from src.modules.consultation.infrastructure.valkey_signed_cache import (
        ValkeySignedCache,
    )

    monkeypatch.setattr(
        composition,
        "get_settings",
        lambda: Settings(SIGNED_CACHE_BACKEND="valkey"),
    )
    cache = composition.get_signed_cache()
    assert isinstance(cache, ValkeySignedCache)
