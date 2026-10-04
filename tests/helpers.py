"""Shared test helpers and database utilities."""

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import get_settings
from src.core.database import engine
from src.modules.auth.application.services.auth_service import AuthService
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.fila_service import FilaService

CLEAN_TABLES_SQL = text(
    "TRUNCATE TABLE documento_itens, documentos_clinicos, evolucoes_clinicas, "
    "triagens, audit_events, atendimentos, dependentes, pacientes, "
    "profissionais, organizacoes, usuarios_credenciais CASCADE;"
)


async def clean_database_tables() -> None:
    """Safely truncate all domain tables respecting foreign keys."""
    async with engine.begin() as conn:
        await conn.execute(CLEAN_TABLES_SQL)


def auth_headers(papel: str, org_id: int, usuario_id: UUID) -> dict[str, str]:
    """Emit real JWT access token header for tests (single decode central)."""
    service = JWTTokenService(secret_key=get_settings().JWT_SECRET_KEY)
    token = service.gerar_tokens(
        usuario_id=usuario_id, organizacao_id=org_id, papel=papel
    ).access_token
    return {"Authorization": f"Bearer {token}"}


def make_auth_service(session: AsyncSession, **overrides: Any) -> AuthService:
    """Build AuthService with AsyncMock fakes unless overridden."""
    hasher: Any = overrides.get("hasher", AsyncMock())
    token_service: Any = overrides.get("token_service", AsyncMock())
    rate_limiter: Any = overrides.get("rate_limiter", AsyncMock())
    return AuthService(
        session=session,
        hasher=hasher,
        token_service=token_service,
        rate_limiter=rate_limiter,
    )


def make_pep_service(session: AsyncSession, **overrides: Any) -> PEPService:
    """Build PEPService with AsyncMock fakes unless overridden."""
    pdf_generator: Any = overrides.get("pdf_generator", AsyncMock())
    signer: Any = overrides.get("signer", AsyncMock())
    storage: Any = overrides.get("storage", AsyncMock())
    return PEPService(
        session=session,
        pdf_generator=pdf_generator,
        signer=signer,
        storage=storage,
    )


def make_alocacao(
    valkey: Any, db_session: AsyncSession, **overrides: Any
) -> AlocacaoChamadaService:
    """Build AlocacaoChamadaService with AsyncMock Lua manager unless overridden."""
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
    alocacao_service: Any = overrides.get("alocacao_service", AsyncMock())
    controle_admissao: Any = overrides.get("controle_admissao", AsyncMock())
    return FilaService(
        valkey=valkey,
        db_session=db_session,
        alocacao_service=alocacao_service,
        controle_admissao=controle_admissao,
    )
