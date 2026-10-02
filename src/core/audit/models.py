"""Immutable append-only audit event model for CFM and LGPD compliance (ADR-007)."""

import ipaddress
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    event,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.audit.exceptions import (
    AuditoriaImutavelError,
    AuditoriaInvalidaError,
)
from src.core.database import Base
from src.core.uuid7 import uuid7

_HEX64_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")


class AtorTipo(StrEnum):
    """Polymorphic actor classification for audit trails."""

    PROFISSIONAL = "PROFISSIONAL"
    PACIENTE = "PACIENTE"
    SISTEMA = "SISTEMA"


class AtorPapel(StrEnum):
    """Specific role or capability exercised during the event."""

    PACIENTE = "PACIENTE"
    MEDICO = "MEDICO"
    GESTOR_UNIDADE = "GESTOR_UNIDADE"
    FATURAMENTO = "FATURAMENTO"
    WORKER_ARQ = "WORKER_ARQ"
    SISTEMA = "SISTEMA"


class AuditEvent(Base):
    """Append-only audit record tracking domain events and state transitions."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "ator_tipo IN ('PROFISSIONAL', 'PACIENTE', 'SISTEMA')",
            name="chk_audit_ator_tipo",
        ),
        Index("idx_audit_atendimento", "atendimento_id", "registrado_em"),
        Index("idx_audit_ator", "organizacao_id", "ator_tipo", "ator_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    atendimento_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("atendimentos.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ator_tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    ator_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ator_papel: Mapped[str] = mapped_column(String(32), nullable=False)
    tipo_evento: Mapped[str] = mapped_column(String(64), nullable=False)
    estado_anterior: Mapped[str | None] = mapped_column(String(32), nullable=True)
    novo_estado: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tcle_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ip_origem: Mapped[str | None] = mapped_column(INET, nullable=True)
    registrado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
        ator_tipo: AtorTipo | str,
        ator_papel: AtorPapel | str,
        tipo_evento: str,
        *,
        ator_id: UUID | None = None,
        estado_anterior: str | None = None,
        novo_estado: str | None = None,
        tcle_hash: str | None = None,
        payload: dict[str, Any] | None = None,
        ip_origem: str | None = None,
        registrado_em: datetime | None = None,
        id: UUID | None = None,
    ) -> None:
        if organizacao_id <= 0:
            raise AuditoriaInvalidaError(
                "organizacao_id inválido: deve ser um identificador positivo."
            )

        if not tipo_evento or not tipo_evento.strip():
            raise AuditoriaInvalidaError(
                "tipo_evento é obrigatório e não pode ser vazio."
            )

        try:
            tipo_enum = (
                ator_tipo
                if isinstance(ator_tipo, AtorTipo)
                else AtorTipo(str(ator_tipo).strip().upper())
            )
        except ValueError as err:
            raise AuditoriaInvalidaError(f"ator_tipo inválido: '{ator_tipo}'.") from err

        try:
            papel_enum = (
                ator_papel
                if isinstance(ator_papel, AtorPapel)
                else AtorPapel(str(ator_papel).strip().upper())
            )
        except ValueError as err:
            raise AuditoriaInvalidaError(
                f"ator_papel inválido: '{ator_papel}'."
            ) from err

        # Atores humanos (PROFISSIONAL, PACIENTE) obrigatoriamente exigem ator_id
        if tipo_enum in (AtorTipo.PROFISSIONAL, AtorTipo.PACIENTE) and ator_id is None:
            raise AuditoriaInvalidaError(
                f"Ator do tipo '{tipo_enum.value}' exige identificador 'ator_id'."
            )

        clean_tcle: str | None = None
        if tcle_hash is not None and tcle_hash.strip():
            th = tcle_hash.strip().lower()
            if len(th) != 64 or not _HEX64_REGEX.match(th):
                raise AuditoriaInvalidaError(
                    f"Hash do TCLE inválido: '{tcle_hash}'. "
                    "Deve conter exatamente 64 caracteres hexadecimais (SHA-256)."
                )
            clean_tcle = th

        clean_ip: str | None = None
        if ip_origem is not None and ip_origem.strip():
            try:
                ip_obj = ipaddress.ip_address(ip_origem.strip())
                clean_ip = str(ip_obj)
            except ValueError as err:
                raise AuditoriaInvalidaError(
                    f"Endereço IP de origem inválido: '{ip_origem}'."
                ) from err

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            atendimento_id=atendimento_id,
            ator_tipo=tipo_enum.value,
            ator_id=ator_id,
            ator_papel=papel_enum.value,
            tipo_evento=tipo_evento.strip(),
            estado_anterior=estado_anterior.strip() if estado_anterior else None,
            novo_estado=novo_estado.strip() if novo_estado else None,
            tcle_hash=clean_tcle,
            payload=payload if payload is not None else {},
            ip_origem=clean_ip,
            registrado_em=registrado_em or datetime.now(UTC),
        )


@event.listens_for(AuditEvent, "before_update")
def impedir_update_audit_event(
    _mapper: Any, _connection: Any, _target: AuditEvent
) -> None:
    raise AuditoriaImutavelError(
        "A tabela audit_events é estritamente append-only (CFM 2.314/2022 e "
        "LGPD Art. 11). Operações de UPDATE são terminantemente proibidas."
    )


@event.listens_for(AuditEvent, "before_delete")
def impedir_delete_audit_event(
    _mapper: Any, _connection: Any, _target: AuditEvent
) -> None:
    raise AuditoriaImutavelError(
        "A tabela audit_events é estritamente append-only (CFM 2.314/2022 e "
        "LGPD Art. 11). Operações de DELETE são terminantemente proibidas."
    )
