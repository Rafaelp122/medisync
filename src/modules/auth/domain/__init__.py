"""Auth domain layer re-exports."""

from src.modules.auth.domain.exceptions import (
    AuthError,
    ContaBloqueadaError,
    ContaDesativadaError,
    CredenciaisInvalidasError,
    TokenExpiradoError,
    TokenInvalidoError,
    TokenRevogadoError,
)
from src.modules.auth.domain.models import UsuarioCredencial

__all__ = [
    "AuthError",
    "ContaBloqueadaError",
    "ContaDesativadaError",
    "CredenciaisInvalidasError",
    "TokenExpiradoError",
    "TokenInvalidoError",
    "TokenRevogadoError",
    "UsuarioCredencial",
]
