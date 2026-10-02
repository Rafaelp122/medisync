"""Domain layer for consultation module."""

from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
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
    "ConsultaFinalizadaError",
    "ConsultaInvalidaError",
    "DocumentoClinico",
    "DocumentoItem",
    "EvolucaoClinica",
    "PrescricaoFisicaObrigatoriaError",
    "PrescricaoFisicaObrigatoriaException",
    "TipoDocumentoClinico",
    "validar_substancia_permitida_telemedicina",
]
