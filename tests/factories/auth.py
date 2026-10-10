"""Typed model factories for authentication entities used across tests."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role
from src.core.uuid7 import uuid7
from src.modules.auth.application.dtos import CadastrarCredencialCommand
from src.modules.auth.application.ports.password_hasher_port import (
    PasswordHasherPort,
)
from src.modules.auth.domain.models import UsuarioCredencial
from src.modules.auth.infrastructure.argon2_hasher import Argon2PasswordHasher

# Hash Argon2id pré-computado para "SenhaForte123!@#" (acelera instâncias em memória)
DEFAULT_TEST_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$anVzdGFzYWx0MTIzNA$e8a0yY/2lO4sB9p2v8bA5w"
)


def make_usuario_credencial(
    organizacao_id: int = 1,
    usuario_id: UUID | None = None,
    *,
    identificador: str = "dr.plantonista@medisync.local",
    senha_hash: str = DEFAULT_TEST_HASH,
    papel: str = Role.MEDICO,
    ativo: bool = True,
    id: UUID | None = None,
) -> UsuarioCredencial:
    """Create a typed in-memory UsuarioCredencial instance for unit tests."""
    return UsuarioCredencial(
        organizacao_id=organizacao_id,
        usuario_id=usuario_id or uuid7(),
        identificador=identificador,
        senha_hash=senha_hash,
        papel=papel,
        ativo=ativo,
        id=id or uuid7(),
    )


def make_cadastrar_credencial_command(
    organizacao_id: int = 1,
    usuario_id: UUID | None = None,
    *,
    identificador: str = "dr.plantonista@medisync.local",
    senha_pura: str = "SenhaForte123!@#",
    papel: str = Role.MEDICO,
) -> CadastrarCredencialCommand:
    """Create a typed CadastrarCredencialCommand DTO."""
    return CadastrarCredencialCommand(
        organizacao_id=organizacao_id,
        usuario_id=usuario_id or uuid7(),
        identificador=identificador,
        senha_pura=senha_pura,
        papel=papel,
    )


async def persist_credencial(
    session: AsyncSession,
    organizacao_id: int = 1,
    usuario_id: UUID | None = None,
    *,
    identificador: str = "dr.plantonista@medisync.local",
    senha_pura: str = "SenhaForte123!@#",
    papel: str = Role.MEDICO,
    hasher: PasswordHasherPort | None = None,
) -> UsuarioCredencial:
    """Persist a real hashed credential to the database for integration tests."""
    active_hasher = hasher or Argon2PasswordHasher()
    hashed = active_hasher.hash(senha_pura)
    cred = make_usuario_credencial(
        organizacao_id=organizacao_id,
        usuario_id=usuario_id,
        identificador=identificador,
        senha_hash=hashed,
        papel=papel,
    )
    session.add(cred)
    await session.commit()
    await session.refresh(cred)
    return cred
