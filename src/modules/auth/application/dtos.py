"""Data Transfer Objects for the authentication application layer."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class LoginCommand:
    """Input command for authenticating user credentials."""

    organizacao_id: int
    identificador: str
    senha: str
    client_ip: str


@dataclass(frozen=True)
class CadastrarCredencialCommand:
    """Input command for provisioning or resetting an authentication credential."""

    organizacao_id: int
    usuario_id: UUID
    identificador: str
    senha_pura: str
    papel: str


@dataclass(frozen=True)
class TokenPairDTO:
    """Pair of short-lived access token and rotatable refresh token."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int = 900
    refresh_expires_in: int = 604800


@dataclass(frozen=True)
class TokenPayloadDTO:
    """Decoded and validated JWT claims."""

    sub: UUID
    org_id: int
    papel: str
    exp: datetime
    jti: str
    type: str


@dataclass(frozen=True)
class RateLimitResultDTO:
    """Result of an anti-brute force rate limit check."""

    permitido: bool
    tentativas_restantes: int
    retry_after_segundos: int
