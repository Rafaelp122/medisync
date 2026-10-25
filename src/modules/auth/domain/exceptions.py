"""Domain exceptions for the authentication and session module."""

from src.core.errors import (
    DomainError,
    ForbiddenError,
    NotFoundError,
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


class PacienteNaoEncontradoError(NotFoundError):
    """Raised when a patient record is not found within the tenant."""

    title = "Paciente Não Encontrado"
    code = "PACIENTE_NAO_ENCONTRADO"

    def __init__(self, detail: str = "Paciente não encontrado na organização.") -> None:
        super().__init__(detail, title=self.title, code=self.code)


class OtpInvalidoOuExpiradoError(UnauthorizedError):
    """Raised when OTP code is incorrect, missing, expired, or max attempts reached."""

    title = "Código OTP Inválido"
    code = "OTP_INVALIDO"

    def __init__(self, detail: str = "Código OTP incorreto ou expirado.") -> None:
        super().__init__(detail, title=self.title, code=self.code)


class OtpRateLimitExcedidoError(DomainError):
    """Raised when OTP request rate limit has been exceeded."""

    status_code = 429
    title = "Muitas Requisições de OTP"
    code = "OTP_RATE_LIMIT_EXCEEDED"

    def __init__(
        self,
        detail: str = (
            "Limite de solicitações de OTP excedido. Tente novamente mais tarde."
        ),
        *,
        retry_after_segundos: int | None = None,
    ) -> None:
        headers = (
            {"Retry-After": str(retry_after_segundos)}
            if retry_after_segundos is not None
            else None
        )
        super().__init__(
            detail,
            status_code=self.status_code,
            title=self.title,
            code=self.code,
            headers=headers,
        )
        self.retry_after_segundos = retry_after_segundos


class OtpTentativasExcedidasError(DomainError):
    """Raised when maximum failed OTP verification attempts (3) are exceeded.

    Regras: RN-AUT-04, US-02 §2.
    Documentação: docs/explanation/domains/auth-domain.md
    """

    status_code = 429
    title = "Tentativas de OTP Excedidas"
    code = "OTP_TENTATIVAS_EXCEDIDAS"

    def __init__(
        self,
        detail: str = (
            "Número máximo de 3 tentativas excedido. Solicite um novo código."
        ),
        *,
        retry_after_segundos: int = 900,
    ) -> None:
        super().__init__(
            detail,
            status_code=self.status_code,
            title=self.title,
            code=self.code,
            headers={"Retry-After": str(retry_after_segundos)},
        )
        self.retry_after_segundos = retry_after_segundos


__all__ = [
    "AuthError",
    "ContaBloqueadaError",
    "ContaDesativadaError",
    "CredenciaisInvalidasError",
    "OtpInvalidoOuExpiradoError",
    "OtpRateLimitExcedidoError",
    "OtpTentativasExcedidasError",
    "PacienteNaoEncontradoError",
    "TokenExpiradoError",
    "TokenInvalidoError",
    "TokenRevogadoError",
]
