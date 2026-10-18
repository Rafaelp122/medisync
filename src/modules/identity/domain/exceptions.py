"""Domain exceptions for the identity and onboarding module."""

from uuid import UUID

from src.core.errors import (
    BadRequestError,
    ConflictError,
    DomainError,
    NotFoundError,
    TenantInvalidoError,
    UnauthorizedError,
    ValidationError,
)


class PacienteNaoEncontradoError(NotFoundError):
    """Raised when a patient record is not found within the tenant."""

    title = "Paciente Não Encontrado"
    code = "PACIENTE_NAO_ENCONTRADO"

    def __init__(self, detail: str = "Paciente não encontrado na organização.") -> None:
        super().__init__(detail, title=self.title, code=self.code)


class DependenteAutoReferenciaError(BadRequestError):
    """Raised when attempting to link a patient as their own dependent."""

    title = "Vínculo Inválido"
    code = "DEPENDENTE_AUTO_REFERENCIA"

    def __init__(
        self,
        detail: str | None = None,
        titular_id: UUID | str | None = None,
        dependente_id: UUID | str | None = None,
    ) -> None:
        if detail is None:
            if titular_id is not None and dependente_id is not None:
                detail = (
                    f"Paciente titular '{titular_id}' e dependente '{dependente_id}' "
                    "não podem ser a mesma pessoa; esperado dependente distinto."
                )
            else:
                detail = "Paciente não pode ser dependente de si mesmo."
        super().__init__(detail, title=self.title, code=self.code)


class VinculoDependenteExistenteError(ConflictError):
    """Raised when dependent linkage already exists between titular and dependent."""

    title = "Vínculo Já Existente"
    code = "VINCULO_DEPENDENTE_EXISTENTE"

    def __init__(
        self, detail: str = "O vínculo entre titular e dependente já está cadastrado."
    ) -> None:
        super().__init__(detail, title=self.title, code=self.code)


class TokenAcolhimentoInvalidoError(UnauthorizedError):
    """Raised when provisional intake token is missing, invalid or expired."""

    title = "Token de Acolhimento Inválido"
    code = "TOKEN_ACOLHIMENTO_INVALIDO"

    def __init__(
        self, detail: str = "Token de acolhimento inválido ou expirado."
    ) -> None:
        super().__init__(detail, title=self.title, code=self.code)


class IdentificacaoObrigatoriaError(ValidationError):
    """Raised when neither CPF nor CNS is provided for patient registration."""

    title = "Identificação Obrigatória"
    code = "IDENTIFICACAO_OBRIGATORIA"

    def __init__(
        self, detail: str = "É obrigatório fornecer CPF ou CNS para o paciente."
    ) -> None:
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
    ) -> None:
        super().__init__(
            detail, status_code=self.status_code, title=self.title, code=self.code
        )


__all__ = [
    "DependenteAutoReferenciaError",
    "IdentificacaoObrigatoriaError",
    "OtpInvalidoOuExpiradoError",
    "OtpRateLimitExcedidoError",
    "PacienteNaoEncontradoError",
    "TenantInvalidoError",
    "TokenAcolhimentoInvalidoError",
    "VinculoDependenteExistenteError",
]
