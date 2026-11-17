"""SQLAlchemy implementation of IdentityWriterPort for patient registration."""

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ConflictError, NotFoundError, ValidationError
from src.core.privacy import mascarar_cpf
from src.modules.identity.application.ports.identity_reader_port import (
    PacienteAuthLookupData,
    PacienteAuthLookupDTO,
)
from src.modules.identity.application.ports.identity_writer_port import (
    IdentityWriterPort,
)
from src.modules.identity.domain.models import Paciente
from src.modules.identity.domain.models._helpers import clean_digits

logger = logging.getLogger("medisync.identity.writer")

_CONFLICT_PUBLIC_MESSAGE = (
    "Não foi possível concluir o cadastro com os dados informados. "
    "Caso já possua conta, utilize a opção Entrar."
)


def _translate_patient_integrity_error(
    exc: IntegrityError,
    *,
    cpf: str,
    organizacao_id: int,
) -> ConflictError | NotFoundError | ValidationError:
    """Translate PostgreSQL IntegrityError SQLSTATE into accurate domain error."""
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)

    if sqlstate == "23505":
        logger.warning(
            "Conflito de unicidade ao criar paciente "
            "(org_id=%s, cpf=%s, constraint=%s).",
            organizacao_id,
            mascarar_cpf(cpf),
            constraint,
        )
        return ConflictError(_CONFLICT_PUBLIC_MESSAGE)

    if sqlstate == "23503":
        logger.error(
            "Chave estrangeira ausente ao criar paciente (org_id=%s, constraint=%s).",
            organizacao_id,
            constraint,
        )
        return NotFoundError(
            f"Unidade de atendimento '{organizacao_id}' não localizada "
            "para realizar o cadastro."
        )

    logger.exception(
        "Erro de integridade ao criar paciente "
        "(org_id=%s, sqlstate=%s, constraint=%s).",
        organizacao_id,
        sqlstate,
        constraint,
    )
    return ValidationError(
        "Não foi possível validar os dados para concluir o cadastro do paciente."
    )


class SqlIdentityWriter(IdentityWriterPort):
    """SQLAlchemy writer creating patient entities within an active transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def criar_paciente(
        self,
        *,
        organizacao_id: int,
        cpf: str,
        nome_completo: str,
        data_nascimento: date,
        telefone: str,
    ) -> PacienteAuthLookupDTO:
        """Create a new Paciente in the organization without committing.

        Transaction ownership remains in the caller Application Service (ADR-001 §6).
        """
        clean_cpf = clean_digits(cpf)
        stmt = select(Paciente).where(
            Paciente.organizacao_id == organizacao_id,
            Paciente.cpf == clean_cpf,
        )
        existing = (await self._session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            logger.warning(
                "Tentativa de cadastro duplicado para CPF '%s' na organização '%s'.",
                mascarar_cpf(clean_cpf),
                organizacao_id,
            )
            raise ConflictError(_CONFLICT_PUBLIC_MESSAGE)

        paciente = Paciente(
            organizacao_id=organizacao_id,
            cpf=clean_cpf,
            nome_completo=nome_completo,
            data_nascimento=data_nascimento,
            telefone=telefone,
        )
        self._session.add(paciente)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise _translate_patient_integrity_error(
                exc,
                cpf=clean_cpf,
                organizacao_id=organizacao_id,
            ) from exc

        return PacienteAuthLookupData(
            id=paciente.id,
            organizacao_id=paciente.organizacao_id,
            telefone=paciente.telefone,
            cpf=paciente.cpf,
            nome_completo=paciente.nome_completo or "",
            nome_mae=paciente.nome_mae,
        )
