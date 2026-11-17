"""SQLAlchemy repository for patient credentials in UsuarioCredencial."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ConflictError, NotFoundError, ValidationError
from src.modules.auth.application.ports.patient_credential_repository_port import (
    PatientCredentialRepositoryPort,
)
from src.modules.auth.domain.models.usuario_credencial import UsuarioCredencial

logger = logging.getLogger("medisync.auth.credentials")


def _translate_credential_integrity_error(
    exc: IntegrityError,
    *,
    organizacao_id: int,
) -> ConflictError | NotFoundError | ValidationError:
    """Translate PostgreSQL IntegrityError SQLSTATE into accurate domain error."""
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)

    if sqlstate == "23505":
        logger.warning(
            "Conflito de credencial ao persistir conta (org_id=%s, constraint=%s).",
            organizacao_id,
            constraint,
        )
        return ConflictError(
            "Não foi possível concluir o cadastro com os dados informados. "
            "Caso já possua conta, utilize a opção Entrar."
        )

    if sqlstate == "23503":
        logger.error(
            "Chave estrangeira ausente ao persistir credencial "
            "(org_id=%s, constraint=%s).",
            organizacao_id,
            constraint,
        )
        return NotFoundError(
            f"Unidade de atendimento '{organizacao_id}' não localizada "
            "para realizar o cadastro."
        )

    logger.exception(
        "Erro de integridade ao persistir credencial "
        "(org_id=%s, sqlstate=%s, constraint=%s).",
        organizacao_id,
        sqlstate,
        constraint,
    )
    return ValidationError(
        "Não foi possível validar os dados da credencial para concluir o cadastro "
        f"(sqlstate={sqlstate!r})."
    )


class SqlPatientCredentialRepository(PatientCredentialRepositoryPort):
    """SQLAlchemy implementation of PatientCredentialRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_por_identificador(
        self,
        organizacao_id: int,
        identificador: str,
        papel: str,
    ) -> UsuarioCredencial | None:
        """Query UsuarioCredencial by tenant, normalized identifier, and role."""
        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.organizacao_id == organizacao_id,
            UsuarioCredencial.identificador == identificador.strip().lower(),
            UsuarioCredencial.papel == papel.strip().upper(),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def buscar_por_usuario_id(
        self,
        organizacao_id: int,
        usuario_id: UUID,
        papel: str,
    ) -> UsuarioCredencial | None:
        """Query UsuarioCredencial by tenant, user UUID, and role."""
        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.organizacao_id == organizacao_id,
            UsuarioCredencial.usuario_id == usuario_id,
            UsuarioCredencial.papel == papel.strip().upper(),
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def existe_identificador(
        self,
        organizacao_id: int,
        identificador: str,
    ) -> bool:
        """Return True if identifier already exists in the organization."""
        stmt = select(UsuarioCredencial.id).where(
            UsuarioCredencial.organizacao_id == organizacao_id,
            UsuarioCredencial.identificador == identificador.strip().lower(),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def criar_credencial(
        self,
        credencial: UsuarioCredencial,
    ) -> UsuarioCredencial:
        """Persist a new UsuarioCredencial without committing."""
        self._session.add(credencial)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise _translate_credential_integrity_error(
                exc,
                organizacao_id=credencial.organizacao_id,
            ) from exc
        return credencial
