"""Pydantic v2 schemas for authentication endpoints."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.auth.application.dtos import (
    AutenticarCadsusInputDTO,
    SolicitarOtpInputDTO,
    VerificarOtpInputDTO,
)


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
    organizacao_id: int | None = Field(
        default=None,
        description=(
            "ID da organização (se omitido, resolvido via cabeçalho X-Tenant-ID)"
        ),
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


class MfaSetupResponse(BaseModel):
    """Response containing TOTP secret and QR Code URI."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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

    refresh_token: str = Field(
        min_length=10,
        description="Token de atualização válido emitido no login ou rotação anterior",
    )


class UsuarioPerfilResponse(BaseModel):
    """Current authenticated user profile claims."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    usuario_id: UUID
    organizacao_id: int
    identificador: str
    papel: str
    ativo: bool


class SolicitarOtpRequest(SolicitarOtpInputDTO):
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


class VerificarOtpRequest(VerificarOtpInputDTO):
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


class AutenticarCadsusRequest(AutenticarCadsusInputDTO, BaseModel):
    """Payload to authenticate patient via CADSUS / Gov.br civil registry."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    cpf: str | None = Field(
        default=None,
        max_length=14,
        description="CPF do paciente (opcional se CNS fornecido)",
        examples=["11144477735"],
    )
    cns: str | None = Field(
        default=None,
        max_length=15,
        description="Cartão Nacional de Saúde (CNS) de 15 dígitos",
        examples=["898001234567890"],
    )
    data_nascimento: date | None = Field(
        default=None,
        description="Data de nascimento do paciente (AAAA-MM-DD)",
        examples=["1985-04-12"],
    )
    nome_mae: str | None = Field(
        default=None,
        max_length=200,
        description="Nome completo da mãe para desambiguação",
        examples=["Maria da Silva"],
    )
