"""Domain exceptions for the authentication and session module."""

from src.core.errors import (
    DomainError,
    ForbiddenError,
    TokenRevogadoError,
    UnauthorizedError,
)


class AuthError(DomainError):
    """Base class for all authentication domain errors."""

    title = "Erro de Autenticação"
    code = "AUTH_ERROR"


class CredenciaisInvalidasError(UnauthorizedError):
    """Raised when identifier/password check fails (generic message per OWASP)."""

    title = "Credenciais Inválidas"
    code = "CREDENCIAIS_INVALIDAS"

    def __init__(
        self,
        detail: str = "Credenciais de autenticação inválidas.",
    ) -> None:
        super().__init__(detail, title=self.title, code=self.code)


class ContaBloqueadaError(DomainError):
    """Raised when an account is temporarily locked due to consecutive failures."""

    status_code = 423
    title = "Conta Bloqueada"
    code = "CONTA_BLOQUEADA"

    def __init__(
        self,
        detail: str = (
            "Conta temporariamente bloqueada por excesso de tentativas falhas. "
            "Tente novamente mais tarde."
        ),
    ) -> None:
        super().__init__(
            detail,
            status_code=self.status_code,
            title=self.title,
            code=self.code,
        )


class ContaDesativadaError(ForbiddenError):
    """Raised when an inactive user credential attempts authentication."""

    title = "Conta Desativada"
    code = "CONTA_DESATIVADA"

    def __init__(
        self,
        detail: str = "A conta informada está inativa.",
    ) -> None:
        super().__init__(detail, title=self.title, code=self.code)


class TokenInvalidoError(UnauthorizedError):
    """Raised when JWT token signature, payload, or structure is invalid."""

    title = "Token Inválido"
    code = "TOKEN_INVALIDO"

    def __init__(
        self,
        detail: str = "Token de autenticação inválido ou malformado.",
    ) -> None:
        super().__init__(detail, title=self.title, code=self.code)


class TokenExpiradoError(UnauthorizedError):
    """Raised when JWT token has expired."""

    title = "Token Expirado"
    code = "TOKEN_EXPIRADO"

    def __init__(
        self,
        detail: str = "Token de autenticação expirado.",
    ) -> None:
        super().__init__(detail, title=self.title, code=self.code)


__all__ = [
    "AuthError",
    "ContaBloqueadaError",
    "ContaDesativadaError",
    "CredenciaisInvalidasError",
    "TokenExpiradoError",
    "TokenInvalidoError",
    "TokenRevogadoError",
]
