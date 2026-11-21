"""Shared test helpers and database utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

from sqlalchemy import text
from src.core.config import get_settings
from src.core.database import get_engine

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession
    from src.modules.auth.application.services.auth_service import AuthService
    from src.modules.consultation.application.services.pep_service import PEPService
    from src.modules.queue.application.services.alocacao_service import (
        AlocacaoChamadaService,
    )
    from src.modules.queue.application.services.fila_service import FilaService

CLEAN_TABLES_SQL = text(
    "TRUNCATE TABLE agendamentos, agenda_disponibilidades, "
    "configuracoes_plantao, producoes_ambulatoriais, "
    "paciente_passkeys, documento_itens, "
    "documentos_clinicos, evolucoes_clinicas, triagens, audit_events, "
    "atendimentos, dependentes, pacientes, profissionais, configuracoes_unidade, "
    "usuarios_credenciais CASCADE;"
)


async def clean_database_tables() -> None:
    """Safely truncate all domain tables respecting foreign keys."""
    async with get_engine().begin() as conn:
        await conn.execute(CLEAN_TABLES_SQL)


DEFAULT_VALKEY_TEST_PATTERNS: tuple[str, ...] = (
    "fila:*",
    "lock:*",
    "plantao:*",
    "cota:*",
    "arq:*",
    "test_org:*",
    "auth:ratelimit:*",
    "otp:*",
    "ratelimit:otp:*",
    "telemetry:*",
    "liveness:*",
    "webauthn:*",
)


async def clean_valkey_keys(*patterns: str) -> None:
    """Clean test keys from Valkey based on patterns or default test namespaces."""
    from src.core.valkey import get_valkey_client

    pats = patterns or DEFAULT_VALKEY_TEST_PATTERNS
    async for client in get_valkey_client():
        all_keys: list[str] = []
        for pat in pats:
            matched: list[str] = await client.keys(pat)  # pyright: ignore[reportUnknownMemberType]
            if matched:
                all_keys.extend(matched)
        if all_keys:
            await client.delete(*all_keys)


async def clean_database_and_valkey(*valkey_patterns: str) -> None:
    """Safely truncate domain database tables and clean Valkey test keys."""
    await clean_database_tables()
    await clean_valkey_keys(*valkey_patterns)


def auth_headers(papel: str, usuario_id: UUID) -> dict[str, str]:
    """Emit real JWT access token header for tests (single decode central)."""
    from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService

    service = JWTTokenService(secret_key=get_settings().JWT_SECRET_KEY)
    token = service.gerar_tokens(usuario_id=usuario_id, papel=papel).access_token
    return {"Authorization": f"Bearer {token}"}


def make_auth_service(session: AsyncSession, **overrides: Any) -> AuthService:
    """Build AuthService with AsyncMock fakes unless overridden."""
    from src.core.authz.revocation import MemoryTokenRevocation
    from src.modules.auth.application.services.auth_service import AuthService

    hasher: Any = overrides.get("hasher", AsyncMock())
    token_service: Any = overrides.get("token_service", AsyncMock())
    rate_limiter: Any = overrides.get("rate_limiter", AsyncMock())
    revocation: Any = overrides.get("revocation", MemoryTokenRevocation())
    return AuthService(
        session=session,
        hasher=hasher,
        token_service=token_service,
        rate_limiter=rate_limiter,
        revocation=revocation,
    )


def make_pep_service(session: AsyncSession, **overrides: Any) -> PEPService:
    """Build PEPService with AsyncMock fakes unless overridden."""
    from src.modules.consultation.application.services.documento_service import (
        DocumentoService,
    )
    from src.modules.consultation.application.services.evolucao_service import (
        EvolucaoService,
    )
    from src.modules.consultation.application.services.pep_service import PEPService
    from src.modules.consultation.infrastructure.memory_signed_cache import (
        MemorySignedCache,
    )

    pdf_generator: Any = overrides.get("pdf_generator", AsyncMock())
    signer: Any = overrides.get("signer", AsyncMock())
    storage: Any = overrides.get("storage", AsyncMock())
    cache: Any = overrides.get("cache", MemorySignedCache())
    atendimento_reader: Any = overrides.get("atendimento_reader")
    if atendimento_reader is None:
        if isinstance(session, AsyncMock):
            atendimento_reader = AsyncMock()
            atendimento_reader.obter_resumo.return_value = None
        else:
            from src.modules.consultation.composition import (
                QueueStoreAtendimentoReaderAdapter,
            )
            from src.modules.queue.composition import build_fila_service_for_session

            queue_store: Any = build_fila_service_for_session(session=session)
            atendimento_reader = QueueStoreAtendimentoReaderAdapter(queue_store)

    audit_trail: Any = overrides.get("audit_trail")
    producao_port: Any = overrides.get("producao_port")
    liveness_verifier: Any = overrides.get("liveness_verifier")
    documento_service: Any = overrides.get("documento_service")
    if documento_service is None:
        directory: Any = overrides.get("directory")
        documento_service = DocumentoService(
            session=session,
            pdf_generator=pdf_generator,
            signer=signer,
            storage=storage,
            cache=cache,
            atendimento_reader=atendimento_reader,
            directory=directory,
            audit_trail=audit_trail,
            liveness_verifier=liveness_verifier,
        )
    evolucao_service: Any = overrides.get("evolucao_service")
    if evolucao_service is None:
        evolucao_service = EvolucaoService(
            session=session,
            reader=atendimento_reader,
            audit_trail=audit_trail,
        )
    return PEPService(
        session=session,
        pdf_generator=pdf_generator,
        signer=signer,
        storage=storage,
        documento_service=documento_service,
        atendimento_reader=atendimento_reader,
        evolucao_service=evolucao_service,
        audit_trail=audit_trail,
        producao_port=producao_port,
    )


def make_alocacao(
    valkey: Any, db_session: AsyncSession, **overrides: Any
) -> AlocacaoChamadaService:
    """Build AlocacaoChamadaService with AsyncMock Lua manager unless overridden."""
    from src.modules.queue.application.services.alocacao_service import (
        AlocacaoChamadaService,
    )

    lua_manager: Any = overrides.get("lua_manager", AsyncMock())
    arq_pool: Any = overrides.get("arq_pool")
    notification_adapter: Any = overrides.get("notification_adapter")
    return AlocacaoChamadaService(
        valkey=valkey,
        db_session=db_session,
        lua_manager=lua_manager,
        arq_pool=arq_pool,
        notification_adapter=notification_adapter,
    )


def make_fila_service(
    valkey: Any, db_session: AsyncSession, **overrides: Any
) -> FilaService:
    """Build FilaService with AsyncMock collaborators unless overridden."""
    from src.modules.queue.application.services.fila_service import FilaService

    alocacao_service: Any = overrides.get("alocacao_service", AsyncMock())
    controle_admissao: Any = overrides.get("controle_admissao", AsyncMock())
    return FilaService(
        valkey=valkey,
        db_session=db_session,
        alocacao_service=alocacao_service,
        controle_admissao=controle_admissao,
    )
