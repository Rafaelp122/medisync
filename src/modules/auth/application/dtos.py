"""Data Transfer Objects for the authentication application layer."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
    mfa_requerido: bool = False


@dataclass(frozen=True)
class TokenPayloadDTO:
    """Decoded and validated JWT claims."""

    sub: UUID
    org_id: int
    papel: str
    exp: datetime
    jti: str
    type: str
    mfa_pending: bool = False


@dataclass(frozen=True)
class MfaSetupDTO:
    """Setup data for registering a TOTP authenticator app."""

    secret: str
    uri: str


@dataclass(frozen=True)
class AtivarMfaCommand:
    """Command to activate second-factor TOTP for a user."""

    usuario_id: UUID
    organizacao_id: int
    codigo: str


@dataclass(frozen=True)
class VerificarMfaLoginCommand:
    """Command to exchange temporary MFA token for final token pair."""

    temp_token: str
    codigo: str


@dataclass(frozen=True)
class RateLimitResultDTO:
    """Result of an anti-brute force rate limit check."""

    permitido: bool
    tentativas_restantes: int
    retry_after_segundos: int


class SolicitarOtpInputDTO(BaseModel):
    """Input parameters for patient OTP request."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    telefone: str
    cpf: str | None = None


class SolicitarOtpOutputDTO(BaseModel):
    """Output results for patient OTP request."""

    model_config = ConfigDict(frozen=True)

    mensagem: str
    expira_em_segundos: int
    codigo_debug: str | None = None


class VerificarOtpInputDTO(BaseModel):
    """Input parameters for patient OTP code verification."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    telefone: str
    codigo: str


class VerificarOtpOutputDTO(BaseModel):
    """Output results containing issued patient JWT access token."""

    model_config = ConfigDict(frozen=True)

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    paciente_id: UUID
    role: str = "PACIENTE"


class AutenticarCadsusInputDTO(BaseModel):
    """Input parameters for CADSUS/Gov.br passwordless civil registry lookup."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    cpf: str | None = None
    cns: str | None = None
    data_nascimento: date | None = None
    nome_mae: str | None = None
