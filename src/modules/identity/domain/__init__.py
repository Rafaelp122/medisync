"""Domain layer for identity module."""

from src.modules.identity.domain.exceptions import (
    DependenteAutoReferenciaError,
    IdentificacaoObrigatoriaError,
    PacienteNaoEncontradoError,
    TenantInvalidoError,
    TokenAcolhimentoInvalidoError,
    VinculoDependenteExistenteError,
)
from src.modules.identity.domain.models import (
    Dependente,
    Organizacao,
    Paciente,
    PapelProfissional,
    Profissional,
)

__all__ = [
    "Dependente",
    "DependenteAutoReferenciaError",
    "IdentificacaoObrigatoriaError",
    "Organizacao",
    "Paciente",
    "PacienteNaoEncontradoError",
    "PapelProfissional",
    "Profissional",
    "TenantInvalidoError",
    "TokenAcolhimentoInvalidoError",
    "VinculoDependenteExistenteError",
]
