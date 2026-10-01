"""Domain models for identity module."""

from src.modules.identity.domain.models.dependente import Dependente
from src.modules.identity.domain.models.organizacao import Organizacao
from src.modules.identity.domain.models.paciente import Paciente
from src.modules.identity.domain.models.profissional import (
    PapelProfissional,
    Profissional,
)

__all__ = [
    "Dependente",
    "Organizacao",
    "Paciente",
    "PapelProfissional",
    "Profissional",
]
