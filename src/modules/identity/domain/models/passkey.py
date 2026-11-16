"""WebAuthn / Passkey device credential model for passwordless patient access."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.core.uuid7 import uuid7


class PacientePasskey(Base):
    """Credencial biométrica WebAuthn/FIDO2 vinculada ao prontuário do paciente.

    Regras: RF-01, ADR-005 (Passwordless/FIDO2), LGPD Art. 11 e US-14.
    Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
    """

    __tablename__ = "paciente_passkeys"
    __table_args__ = (
        UniqueConstraint(
            "organizacao_id",
            "credential_id",
            name="uq_paciente_passkeys_org_cred",
        ),
        Index("idx_paciente_passkeys_paciente", "organizacao_id", "paciente_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("organizacoes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paciente_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("pacientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    device_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        paciente_id: UUID,
        credential_id: str,
        public_key: str,
        sign_count: int = 0,
        device_name: str | None = None,
        id: UUID | None = None,
    ) -> None:
        if organizacao_id <= 0:
            raise ValidationError(
                f"organizacao_id inválido: '{organizacao_id}'; esperado inteiro > 0."
            )
        clean_cred = credential_id.strip()
        if not clean_cred:
            raise ValidationError(
                f"credential_id inválido: {credential_id!r}; "
                "esperado identificador não vazio."
            )
        clean_pub = public_key.strip()
        if not clean_pub:
            raise ValidationError(
                f"public_key inválida: {public_key!r}; "
                "esperado chave pública codificada."
            )
        if sign_count < 0:
            raise ValidationError(
                f"sign_count inválido: '{sign_count}'; esperado inteiro >= 0."
            )

        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            paciente_id=paciente_id,
            credential_id=clean_cred,
            public_key=clean_pub,
            sign_count=sign_count,
            device_name=device_name.strip()
            if device_name and device_name.strip()
            else None,
        )

    def atualizar_contador(self, novo_sign_count: int) -> None:
        """Atualiza o contador monotônico de assinatura FIDO2 contra clonagem.

        Regras: RF-01, ADR-005 e US-14 (W3C WebAuthn signCount).
        Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
        """
        if novo_sign_count < 0:
            raise ValidationError(
                f"Contador de assinatura inválido: '{novo_sign_count}'; "
                f"esperado inteiro >= 0 (atual: {self.sign_count})."
            )
        if self.sign_count > 0 and novo_sign_count <= self.sign_count:
            raise ValidationError(
                f"Contador de assinatura regressivo ou estagnado: '{novo_sign_count}'; "
                f"esperado > {self.sign_count} para prevenir clonagem de autenticador."
            )
        self.sign_count = novo_sign_count
