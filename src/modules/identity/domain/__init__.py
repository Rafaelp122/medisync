"""Domain layer for identity module."""

from src.modules.identity.domain.exceptions import (
    DependenteAutoReferenciaError,
    IdentificacaoObrigatoriaError,
    PacienteNaoEncontradoError,
    TokenAcolhimentoInvalidoError,
    VinculoDependenteExistenteError,
)
from src.modules.identity.domain.models import (
    ConfiguracaoUnidade,
    Dependente,
    Paciente,
    PacientePasskey,
    PapelProfissional,
    Profissional,
)

__all__ = [
    "ConfiguracaoUnidade",
    "Dependente",
    "DependenteAutoReferenciaError",
    "IdentificacaoObrigatoriaError",
    "Paciente",
    "PacienteNaoEncontradoError",
    "PacientePasskey",
    "PapelProfissional",
    "Profissional",
    "TokenAcolhimentoInvalidoError",
    "VinculoDependenteExistenteError",
]
