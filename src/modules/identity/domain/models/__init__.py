"""Domain models for identity module."""

from src.modules.identity.domain.models.configuracao_unidade import ConfiguracaoUnidade
from src.modules.identity.domain.models.dependente import Dependente
from src.modules.identity.domain.models.paciente import Paciente
from src.modules.identity.domain.models.passkey import PacientePasskey
from src.modules.identity.domain.models.profissional import (
    PapelProfissional,
    Profissional,
)

__all__ = [
    "ConfiguracaoUnidade",
    "Dependente",
    "Paciente",
    "PacientePasskey",
    "PapelProfissional",
    "Profissional",
]
