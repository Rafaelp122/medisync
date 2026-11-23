"""Domain layer for consultation module."""

from src.modules.consultation.domain.exceptions import (
    AssinaturaDigitalInvalidaError,
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
    DocumentoClinicoNaoEncontradoError,
    DocumentoNaoEncontradoNoStorageError,
    EvolucaoNaoEncontradaError,
    IANaoRatificadaError,
    PrescricaoFisicaObrigatoriaError,
    TravaAntiFraudeAtestadoError,
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
    "DocumentoClinicoNaoEncontradoError",
    "DocumentoItem",
    "DocumentoNaoEncontradoNoStorageError",
    "EvolucaoClinica",
    "EvolucaoNaoEncontradaError",
    "IANaoRatificadaError",
    "PrescricaoFisicaObrigatoriaError",
    "TipoDocumentoClinico",
    "TravaAntiFraudeAtestadoError",
    "validar_substancia_permitida_telemedicina",
]
