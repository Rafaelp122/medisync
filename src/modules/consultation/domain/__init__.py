"""Domain layer for consultation module."""

from src.modules.consultation.domain.exceptions import (
    AssinaturaDigitalInvalidaError,
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
    DocumentoNaoEncontradoNoStorageError,
    PrescricaoFisicaObrigatoriaError,
    PrescricaoFisicaObrigatoriaException,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    DocumentoItem,
    EvolucaoClinica,
    TipoDocumentoClinico,
    validar_substancia_permitida_telemedicina,
)

__all__ = [
    "AssinaturaDigitalInvalidaError",
    "ConsultaFinalizadaError",
    "ConsultaInvalidaError",
    "DocumentoClinico",
    "DocumentoItem",
    "DocumentoNaoEncontradoNoStorageError",
    "EvolucaoClinica",
    "PrescricaoFisicaObrigatoriaError",
    "PrescricaoFisicaObrigatoriaException",
    "TipoDocumentoClinico",
    "validar_substancia_permitida_telemedicina",
]
