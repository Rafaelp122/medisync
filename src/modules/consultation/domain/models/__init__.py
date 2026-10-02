"""Domain models for consultation module."""

from src.modules.consultation.domain.models._substances import (
    validar_substancia_permitida_telemedicina,
)
from src.modules.consultation.domain.models.documento_clinico import (
    DocumentoClinico,
    TipoDocumentoClinico,
)
from src.modules.consultation.domain.models.documento_item import DocumentoItem
from src.modules.consultation.domain.models.evolucao_clinica import EvolucaoClinica

__all__ = [
    "DocumentoClinico",
    "DocumentoItem",
    "EvolucaoClinica",
    "TipoDocumentoClinico",
    "validar_substancia_permitida_telemedicina",
]
