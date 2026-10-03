"""Domain exceptions for consultation, clinical evolutions and prescriptions."""

from src.core.errors import DomainError, NotFoundError, ValidationError


class PrescricaoFisicaObrigatoriaError(ValidationError):
    """Raised when medication requires physical pads (Portaria 344/98 Listas A/B)."""

    status_code: int = 422
    title: str = "Prescrição Física Obrigatória — Exigência de Notificação em Papel"
    code: str = "PRESCRICAO_FISICA_OBRIGATORIA"


# Compatibility alias
PrescricaoFisicaObrigatoriaException = PrescricaoFisicaObrigatoriaError


class ConsultaFinalizadaError(DomainError):
    """Raised when attempting to modify/delete records of finalized consultation."""

    status_code: int = 409
    title: str = "Consulta Finalizada — Registro Clínico Imutável"
    code: str = "CONSULTA_FINALIZADA_IMUTAVEL"


class ConsultaInvalidaError(ValidationError):
    """Raised when clinical evolution or prescription violates domain rules."""

    status_code: int = 422
    title: str = "Registro de Consulta Inválido"
    code: str = "CONSULTA_INVALIDA"


class AssinaturaDigitalInvalidaError(DomainError):
    """Raised when digital signing fails or returns invalid signature."""

    status_code: int = 422
    title: str = "Falha na Assinatura Digital ICP-Brasil"
    code: str = "ASSINATURA_DIGITAL_INVALIDA"


class DocumentoNaoEncontradoNoStorageError(NotFoundError):
    """Raised when an object key is not found in Object Storage."""

    status_code: int = 404
    title: str = "Documento Não Encontrado no Storage"
    code: str = "DOCUMENTO_STORAGE_NAO_ENCONTRADO"
