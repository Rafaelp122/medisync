"""Pydantic v2 schemas for authentication endpoints."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    """Payload for user credentials authentication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    identificador: str = Field(
        min_length=3,
        max_length=255,
        description="E-mail corporativo ou CPF limpo",
        examples=["dr.roberto@telemed.com.br", "12345678901"],
    )
    senha: str = Field(
        min_length=1,
        max_length=128,
        description="Senha em texto puro",
    )


class TokenResponse(BaseModel):
    """Access and refresh tokens pair response."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    access_token: str = Field(description="JWT Bearer token de curta duração (15 min)")
    refresh_token: str = Field(
        description="Token de atualização rotacionável de uso único (7 dias)"
    )
    token_type: str = Field(
        default="bearer", description="Esquema de autenticação HTTP"
    )
    expires_in: int = Field(description="Tempo de vida do access token em segundos")
    refresh_expires_in: int = Field(
        description="Tempo de vida do refresh token em segundos"
    )
    mfa_requerido: bool = Field(
        default=False,
        description="Indica se é necessária autenticação de segundo fator (MFA/TOTP)",
    )
    mfa_setup_requerido: bool = Field(
        default=False,
        description=(
            "Indica se é necessária configuração inicial de segundo fator (MFA/TOTP)"
        ),
    )


class MfaSetupResponse(BaseModel):
    """Response containing TOTP secret and QR Code URI."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    secret: str = Field(description="Chave secreta Base32 do autenticador")
    uri: str = Field(description="URI otpauth:// para escaneamento de QR Code")


class MfaAtivarRequest(BaseModel):
    """Payload to confirm TOTP setup and activate MFA."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    codigo: str = Field(
        min_length=6,
        max_length=6,
        description="Código numérico de 6 dígitos gerado pelo aplicativo autenticador",
        examples=["123456"],
    )


class MfaAtivarResponse(BaseModel):
    """Response returned upon successful MFA activation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ativo: bool = Field(
        default=True, description="Indica se o MFA foi ativado com sucesso"
    )
    mensagem: str = Field(
        default="Segundo fator de autenticação ativado com sucesso.",
        description="Mensagem de confirmação",
    )


class MfaVerificarLoginRequest(BaseModel):
    """Payload to complete two-factor authentication login."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temp_token: str = Field(
        min_length=10,
        description="Token temporário emitido na primeira etapa de autenticação",
    )
    codigo: str = Field(
        min_length=6,
        max_length=6,
        description="Código TOTP de 6 dígitos do autenticador",
        examples=["123456"],
    )


class RefreshTokenRequest(BaseModel):
    """Payload for rotating refresh token."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    refresh_token: str | None = Field(
        default=None,
        min_length=10,
        description="Token de atualização válido emitido no login ou rotação anterior",
    )


class UsuarioPerfilResponse(BaseModel):
    """Current authenticated user profile claims."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    usuario_id: UUID
    identificador: str
    papel: str
    ativo: bool


class SolicitarOtpRequest(BaseModel):
    """Payload to request an OTP code via SMS."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    telefone: str = Field(
        min_length=10,
        max_length=20,
        description="Telefone de contato com DDD",
        examples=["11987654321"],
    )
    cpf: str | None = Field(
        default=None,
        max_length=14,
        description="CPF do paciente (opcional, para desambiguação)",
        examples=["11144477735"],
    )


class SolicitarOtpResponse(BaseModel):
    """Response returned upon OTP request dispatch."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    mensagem: str
    expira_em_segundos: int
    codigo_debug: str | None = None


class VerificarOtpRequest(BaseModel):
    """Payload to verify OTP code and obtain patient access token."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    telefone: str = Field(
        min_length=10,
        max_length=20,
        description="Telefone de contato com DDD",
        examples=["11987654321"],
    )
    codigo: str = Field(
        min_length=6,
        max_length=6,
        description="Código OTP de 6 dígitos numéricos",
        examples=["123456"],
    )


class VerificarOtpResponse(BaseModel):
    """Response containing issued patient Bearer JWT token."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    paciente_id: UUID
    role: str = Field(
        default="PACIENTE",
        description="Papel do usuário autenticado no sistema",
        examples=["PACIENTE"],
    )
    atendimento_id: UUID | None = Field(
        default=None,
        description=(
            "ID do atendimento ativo do paciente (opcional para reconexão em /fila)"
        ),
    )


class AutenticarCadsusRequest(BaseModel):
    """Payload to authenticate patient via CADSUS / Gov.br with 2nd civil factor."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    cpf: str | None = Field(
        default=None,
        max_length=14,
        description="CPF do paciente (requer nome_mae ou cns adicional)",
        examples=["11144477735"],
    )
    cns: str | None = Field(
        default=None,
        max_length=18,
        description="Cartão Nacional de Saúde (CNS) de 15 dígitos",
        examples=["800000000000001"],
    )
    data_nascimento: date = Field(
        description="Data de nascimento do paciente (AAAA-MM-DD, obrigatória)",
        examples=["1985-04-12"],
    )
    nome_mae: str | None = Field(
        default=None,
        max_length=200,
        description="Nome da mãe (obrigatório quando autenticando apenas por CPF)",
        examples=["Maria da Silva"],
    )

    @model_validator(mode="after")
    def _validar_fatores_civis(self) -> "AutenticarCadsusRequest":
        if not self.cpf and not self.cns:
            raise ValueError(
                "Informe CPF ou CNS válido junto à data de nascimento para "
                f"autenticação CADSUS (recebido cpf={self.cpf!r}, cns={self.cns!r})."
            )
        if self.cpf and not self.cns and not self.nome_mae:
            raise ValueError(
                "Ao autenticar por CPF via CADSUS/Gov.br, informe também 'nome_mae' "
                f"(2º fator civil) ou 'cns' (recebido nome_mae={self.nome_mae!r}, "
                f"cns={self.cns!r})."
            )
        return self


class WebAuthnRpSchema(BaseModel):
    """WebAuthn Relying Party metadata."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    name: str
    id: str


class WebAuthnUserSchema(BaseModel):
    """WebAuthn patient user handle descriptor."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    id: str
    name: str
    displayName: str


class WebAuthnPubKeyCredParamSchema(BaseModel):
    """Supported WebAuthn COSE key algorithm parameter."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    alg: int
    type: str = "public-key"


class WebAuthnAuthenticatorSelectionSchema(BaseModel):
    """WebAuthn authenticator selection enforcing discoverable credentials."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    residentKey: str = "required"
    requireResidentKey: bool = True
    userVerification: str = "preferred"


class WebAuthnRegisterOptionsResponse(BaseModel):
    """PublicKeyCredentialCreationOptions payload for passkey registration."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    challenge: str
    rp: WebAuthnRpSchema
    user: WebAuthnUserSchema
    pubKeyCredParams: list[WebAuthnPubKeyCredParamSchema]
    timeout: int = 60000
    attestation: str = "none"
    authenticatorSelection: WebAuthnAuthenticatorSelectionSchema = (
        WebAuthnAuthenticatorSelectionSchema()
    )


class WebAuthnRegisterVerifyRequest(BaseModel):
    """WebAuthn registration credential attestation submitted by client browser."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=512)
    rawId: str = Field(min_length=1, max_length=1024)
    response: dict[str, object]
    type: str = Field(default="public-key", max_length=32)
    device_name: str | None = Field(default=None, max_length=128)


class WebAuthnRegisterVerifyResponse(BaseModel):
    """Confirmation payload returned after storing a WebAuthn passkey."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    status: str
    credencial_id: str


class WebAuthnAllowCredentialSchema(BaseModel):
    """Permitted credential descriptor for WebAuthn assertion."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    id: str
    type: str = "public-key"


class WebAuthnAuthOptionsRequest(BaseModel):
    """Optional patient filter when requesting WebAuthn authentication options."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    paciente_id: UUID | None = None


class WebAuthnAuthOptionsResponse(BaseModel):
    """PublicKeyCredentialRequestOptions payload for passkey login."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    challenge: str
    rpId: str
    allowCredentials: list[WebAuthnAllowCredentialSchema]
    timeout: int = 60000
    userVerification: str = "preferred"


class WebAuthnAuthVerifyRequest(BaseModel):
    """WebAuthn assertion credential submitted by client browser during login."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=512)
    rawId: str = Field(min_length=1, max_length=1024)
    response: dict[str, object]
    type: str = Field(default="public-key", max_length=32)


class RegistrarPacienteRequest(BaseModel):
    """Payload for citizen self-service registration with mandatory email."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    cpf: str = Field(min_length=11, max_length=14, description="CPF do cidadão")
    nome_completo: str = Field(
        min_length=2, max_length=255, description="Nome completo do cidadão"
    )
    data_nascimento: date = Field(description="Data de nascimento (AAAA-MM-DD)")
    telefone: str = Field(
        min_length=10, max_length=20, description="Telefone celular com DDD"
    )
    email: str = Field(
        min_length=5, max_length=255, description="E-mail obrigatório do cidadão"
    )
    aceite_privacidade: bool = Field(
        description="Aceite explícito da política de privacidade (LGPD)"
    )
    senha: str | None = Field(
        default=None,
        max_length=128,
        description="Senha opcional de acesso (>= 8 caracteres)",
    )


class RegistrarPacienteResponse(BaseModel):
    """Response returned after registering citizen and dispatching initial OTP."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    paciente_id: UUID
    telefone_mascarado: str
    otp_enviado: bool
    expira_em_segundos: int
    codigo_debug: str | None = None


class IdentificarPacienteRequest(BaseModel):
    """Payload for anti-enumeration patient identification lookup."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    identificador: str = Field(
        min_length=3,
        max_length=255,
        description="CPF (11 dígitos) ou e-mail do paciente",
    )


class IdentificarPacienteResponse(BaseModel):
    """Response indicating available patient authentication methods without PII."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    possui_conta: bool
    metodos_disponiveis: list[Literal["otp", "senha", "passkey", "govbr"]]
    telefone_mascarado: str | None = None
    govbr_habilitado: bool


class LoginPacienteSenhaRequest(BaseModel):
    """Payload for traditional patient login with password fallback."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    identificador: str = Field(
        min_length=3,
        max_length=255,
        description="E-mail ou CPF do paciente",
    )
    senha: str = Field(
        min_length=1,
        max_length=128,
        description="Senha em texto puro",
    )


class MetodosAutenticacaoPacienteResponse(BaseModel):
    """Response describing globally enabled patient authentication capabilities."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)

    govbr_oidc_enabled: bool
    passkeys_enabled: bool = True
    otp_enabled: bool = True
    password_fallback_enabled: bool = True
