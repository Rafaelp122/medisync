"""Pydantic v2 schemas for authentication endpoints."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Payload for user credentials authentication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    identificador: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="E-mail corporativo ou CPF limpo",
        examples=["dr.roberto@telemed.com.br", "12345678901"],
    )
    senha: str = Field(
        ...,
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

    access_token: str = Field(
        ..., description="JWT Bearer token de curta duração (15 min)"
    )
    refresh_token: str = Field(
        ..., description="Token de atualização rotacionável de uso único (7 dias)"
    )
    token_type: str = Field(
        default="bearer", description="Esquema de autenticação HTTP"
    )
    expires_in: int = Field(
        ..., description="Tempo de vida do access token em segundos"
    )
    refresh_expires_in: int = Field(
        ..., description="Tempo de vida do refresh token em segundos"
    )


class RefreshTokenRequest(BaseModel):
    """Payload for rotating refresh token."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    refresh_token: str = Field(
        ...,
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
