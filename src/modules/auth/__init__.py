"""Auth module package re-exports."""

from src.modules.auth.application import (
    AuthService,
    CadastrarCredencialCommand,
    LoginCommand,
    RateLimitResultDTO,
    TokenPairDTO,
    TokenPayloadDTO,
)
from src.modules.auth.domain import (
    AuthError,
    ContaBloqueadaError,
    ContaDesativadaError,
    CredenciaisInvalidasError,
    TokenExpiradoError,
    TokenInvalidoError,
    TokenRevogadoError,
    UsuarioCredencial,
)
from src.modules.auth.presentation import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UsuarioPerfilResponse,
    auth_router,
)

__all__ = [
    "AuthError",
    "AuthService",
    "CadastrarCredencialCommand",
    "ContaBloqueadaError",
    "ContaDesativadaError",
    "CredenciaisInvalidasError",
    "LoginCommand",
    "LoginRequest",
    "RateLimitResultDTO",
    "RefreshTokenRequest",
    "TokenExpiradoError",
    "TokenInvalidoError",
    "TokenPairDTO",
    "TokenPayloadDTO",
    "TokenResponse",
    "TokenRevogadoError",
    "UsuarioCredencial",
    "UsuarioPerfilResponse",
    "auth_router",
]
