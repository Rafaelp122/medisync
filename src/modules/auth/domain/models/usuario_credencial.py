"""Rich domain entity for user authentication credentials."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.uuid7 import uuid7


class UsuarioCredencial(Base):
    """User authentication credential entity (Argon2id hash, lockout, role claims)."""

    __tablename__ = "usuarios_credenciais"
    __table_args__ = (
        UniqueConstraint(
            "organizacao_id",
            "identificador",
            name="uq_usuarios_credenciais_org_identificador",
        ),
        Index(
            "idx_usuarios_credenciais_org_papel",
            "organizacao_id",
            "papel",
        ),
        Index("idx_usuarios_credenciais_usuario_id", "usuario_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    usuario_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    identificador: Mapped[str] = mapped_column(String(255), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    papel: Mapped[str] = mapped_column(String(32), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    falhas_login_consecutivas: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    bloqueado_ate: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(
        self,
        organizacao_id: int,
        usuario_id: UUID,
        identificador: str,
        senha_hash: str,
        papel: str,
        ativo: bool = True,
        id: UUID | None = None,
    ) -> None:
        clean_ident = identificador.strip().lower()
        super().__init__(
            id=id or uuid7(),
            organizacao_id=organizacao_id,
            usuario_id=usuario_id,
            identificador=clean_ident,
            senha_hash=senha_hash.strip(),
            papel=papel.strip().upper(),
            ativo=ativo,
            falhas_login_consecutivas=0,
            bloqueado_ate=None,
        )

    def is_bloqueado(self, agora: datetime | None = None) -> bool:
        """Verifica se a conta está em lockout temporário por falhas consecutivas.

        Regras: RN-AUT-04 (auth-domain.md), ADR-007, RF-01.
        """
        if self.bloqueado_ate is None:
            return False
        momento = agora or datetime.now(UTC)
        if momento < self.bloqueado_ate:
            return True
        # Lockout period expired: auto-reset
        self.bloqueado_ate = None
        self.falhas_login_consecutivas = 0
        return False

    def registrar_falha_login(
        self,
        max_falhas: int = 5,
        minutos_bloqueio: int = 15,
        agora: datetime | None = None,
    ) -> bool:
        """Incrementa falhas consecutivas e aplica lockout de 15 min no limiar.

        Regras: docs/explanation/domains/auth-domain.md
        """
        momento = agora or datetime.now(UTC)
        self.falhas_login_consecutivas += 1
        self.atualizado_em = momento
        if self.falhas_login_consecutivas >= max_falhas:
            self.bloqueado_ate = momento + timedelta(minutes=minutos_bloqueio)
            return True
        return False

    def registrar_sucesso_login(self, agora: datetime | None = None) -> None:
        """Reseta contadores de falhas e desbloqueia após autenticação com sucesso.

        Regras: docs/explanation/domains/auth-domain.md
        """
        self.falhas_login_consecutivas = 0
        self.bloqueado_ate = None
        self.atualizado_em = agora or datetime.now(UTC)

    def atualizar_senha(self, novo_hash: str, agora: datetime | None = None) -> None:
        """Atualiza hash Argon2id e reseta contadores de segurança.

        Regras: docs/adrs/ADR-005-Autenticacao-Passwordless-Argon2id.md
        """
        self.senha_hash = novo_hash.strip()
        self.falhas_login_consecutivas = 0
        self.bloqueado_ate = None
        self.atualizado_em = agora or datetime.now(UTC)

    def desativar(self) -> None:
        """Desativa conta impedindo novas sessões (revogação de acesso).

        Regras: docs/explanation/domains/auth-domain.md
        """
        self.ativo = False
        self.atualizado_em = datetime.now(UTC)

    def ativar(self) -> None:
        """Reativa credencial de usuário para autenticação.

        Regras: docs/explanation/domains/auth-domain.md
        """
        self.ativo = True
        self.atualizado_em = datetime.now(UTC)
