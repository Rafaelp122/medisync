"""SQLAlchemy implementation of IdentityWriterPort for patient and passkey writes."""

import logging
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ConflictError, NotFoundError, ValidationError
from src.core.privacy import clean_digits, mascarar_cpf
from src.modules.identity.application.ports.identity_reader_port import (
    PacienteAuthLookupData,
    PacienteAuthLookupDTO,
    PacientePasskeyData,
    PacientePasskeyDTO,
)
from src.modules.identity.application.ports.identity_writer_port import (
    IdentityWriterPort,
)
from src.modules.identity.domain.models import Paciente, PacientePasskey

logger = logging.getLogger("medisync.identity.writer")

_CONFLICT_PUBLIC_MESSAGE = (
    "Não foi possível concluir o cadastro com os dados informados. "
    "Caso já possua conta, utilize a opção Entrar."
)


def _translate_patient_integrity_error(
    exc: IntegrityError,
    *,
    cpf: str,
) -> ConflictError | NotFoundError | ValidationError:
    """Translate PostgreSQL IntegrityError SQLSTATE into accurate domain error."""
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)

    if sqlstate == "23505":
        logger.warning(
            "Conflito de unicidade ao criar paciente (cpf=%s, constraint=%s).",
            mascarar_cpf(cpf),
            constraint,
        )
        return ConflictError(_CONFLICT_PUBLIC_MESSAGE)

    if sqlstate == "23503":
        logger.error(
            "Chave estrangeira ausente ao criar paciente (constraint=%s).",
            constraint,
        )
        return NotFoundError(
            f"Referência associada ao cadastro de paciente não localizada "
            f"(constraint={constraint!r})."
        )

    logger.exception(
        "Erro de integridade ao criar paciente (sqlstate=%s, constraint=%s).",
        sqlstate,
        constraint,
    )
    return ValidationError(
        "Não foi possível validar os dados para concluir o cadastro do paciente "
        f"(sqlstate={sqlstate!r})."
    )


def _to_passkey_data(passkey: PacientePasskey) -> PacientePasskeyData:
    return PacientePasskeyData(
        id=passkey.id,
        paciente_id=passkey.paciente_id,
        credential_id=passkey.credential_id,
        public_key=passkey.public_key,
        sign_count=passkey.sign_count,
        device_name=passkey.device_name,
    )


class SqlIdentityWriter(IdentityWriterPort):
    """SQLAlchemy writer persisting patient and passkey entities in a transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def criar_paciente(
        self,
        *,
        cpf: str,
        nome_completo: str,
        data_nascimento: date,
        telefone: str,
    ) -> PacienteAuthLookupDTO:
        """Create a new Paciente in the platform without committing.

        Transaction ownership remains in the caller Application Service (ADR-001 §6).
        """
        clean_cpf = clean_digits(cpf)
        stmt = select(Paciente).where(Paciente.cpf == clean_cpf)
        existing = (await self._session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            logger.warning(
                "Tentativa de cadastro duplicado para CPF '%s'.",
                mascarar_cpf(clean_cpf),
            )
            raise ConflictError(_CONFLICT_PUBLIC_MESSAGE)

        paciente = Paciente(
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
            ) from exc

        return PacienteAuthLookupData(
            id=paciente.id,
            telefone=paciente.telefone,
            cpf=paciente.cpf,
            nome_completo=paciente.nome_completo or "",
            nome_mae=paciente.nome_mae,
            cns=paciente.cns,
            data_nascimento=paciente.data_nascimento,
        )

    async def registrar_passkey_paciente(
        self,
        paciente_id: UUID,
        credential_id: str,
        public_key: str,
        sign_count: int = 0,
        device_name: str | None = None,
    ) -> PacientePasskeyDTO:
        """Persiste credencial Passkey WebAuthn sem commit (ADR-001 §6).

        Regras: RF-01, ADR-005, ADR-013,
        docs/user-stories/US-14-biometria-passkeys-webauthn.md.
        """
        stmt = select(PacientePasskey).where(
            PacientePasskey.credential_id == credential_id
        )
        existing = (await self._session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(
                f"Credencial WebAuthn '{credential_id}' já registrada na "
                f"plataforma (paciente '{existing.paciente_id}')."
            )

        passkey = PacientePasskey(
            paciente_id=paciente_id,
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            device_name=device_name,
        )
        self._session.add(passkey)
        await self._session.flush()
        return _to_passkey_data(passkey)

    async def atualizar_sign_count_passkey(
        self,
        credential_id: str,
        novo_sign_count: int,
    ) -> PacientePasskeyDTO:
        """Atualiza contador monotônico FIDO2 sem commit (ADR-001 §6).

        Regras: RF-01, ADR-005, ADR-013,
        docs/user-stories/US-14-biometria-passkeys-webauthn.md.
        """
        stmt = select(PacientePasskey).where(
            PacientePasskey.credential_id == credential_id
        )
        passkey = (await self._session.execute(stmt)).scalar_one_or_none()
        if passkey is None:
            raise NotFoundError(
                f"Credencial Passkey '{credential_id}' não encontrada na "
                "plataforma; esperado credential_id registrado."
            )
        passkey.atualizar_contador(novo_sign_count)
        await self._session.flush()
        return _to_passkey_data(passkey)
