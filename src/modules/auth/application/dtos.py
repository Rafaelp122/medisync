"""Data Transfer Objects for the authentication application layer."""

from dataclasses import dataclass, field
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
    mfa_setup_requerido: bool = False


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
    atendimento_id: UUID | None = None


class AutenticarCadsusInputDTO(BaseModel):
    """Input parameters for CADSUS/Gov.br passwordless civil registry lookup."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    cpf: str | None = None
    cns: str | None = None
    data_nascimento: date | None = None
    nome_mae: str | None = None


@dataclass(frozen=True)
class WebAuthnRpDTO:
    """Relying Party metadata for WebAuthn registration options."""

    name: str
    id: str


@dataclass(frozen=True)
class WebAuthnUserDTO:
    """User entity descriptor for WebAuthn credential creation."""

    id: str
    name: str
    displayName: str


@dataclass(frozen=True)
class WebAuthnPubKeyCredParamDTO:
    """Supported COSE algorithm descriptor for WebAuthn public keys."""

    alg: int
    type: str = "public-key"


@dataclass(frozen=True)
class WebAuthnAuthenticatorSelectionDTO:
    """Authenticator selection criteria enforcing discoverable credentials (US-14)."""

    residentKey: str = "required"
    requireResidentKey: bool = True
    userVerification: str = "preferred"


@dataclass(frozen=True)
class WebAuthnRegisterOptionsDTO:
    """Output DTO for WebAuthn passkey registration challenge options (US-14)."""

    challenge: str
    rp: WebAuthnRpDTO
    user: WebAuthnUserDTO
    pubKeyCredParams: list[WebAuthnPubKeyCredParamDTO]
    timeout: int = 60000
    attestation: str = "none"
    authenticatorSelection: WebAuthnAuthenticatorSelectionDTO = (
        WebAuthnAuthenticatorSelectionDTO()
    )


@dataclass(frozen=True)
class WebAuthnRegisterVerifyCommand:
    """Command encapsulating patient passkey attestation payload verification."""

    organizacao_id: int
    paciente_id: UUID
    id: str
    raw_id: str
    response: dict[str, object] = field(default_factory=dict)
    type: str = "public-key"
    device_name: str | None = None


@dataclass(frozen=True)
class WebAuthnRegisterResultDTO:
    """Output DTO confirming registered WebAuthn passkey credential."""

    status: str
    credencial_id: str


@dataclass(frozen=True)
class WebAuthnAllowCredentialDTO:
    """Allowed credential descriptor returned in WebAuthn assertion options."""

    id: str
    type: str = "public-key"


@dataclass(frozen=True)
class WebAuthnAuthOptionsDTO:
    """Output DTO for WebAuthn passkey authentication challenge options (US-14)."""

    challenge: str
    rpId: str
    allowCredentials: list[WebAuthnAllowCredentialDTO]
    timeout: int = 60000
    userVerification: str = "preferred"


@dataclass(frozen=True)
class WebAuthnAuthVerifyCommand:
    """Command encapsulating patient passkey assertion verification."""

    organizacao_id: int
    id: str
    raw_id: str
    response: dict[str, object] = field(default_factory=dict)
    type: str = "public-key"
