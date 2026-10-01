"""Triage domain layer."""

from src.modules.triage.domain.classification import (
    SINAIS_ALARME_NIVEL_1,
    calcular_hash_tcle,
    classificar_risco_clinico,
)
from src.modules.triage.domain.exceptions import (
    EmergenciaCriticaSamuError,
    TriagemInvalidaError,
)
from src.modules.triage.domain.models import Triagem

__all__ = [
    "SINAIS_ALARME_NIVEL_1",
    "EmergenciaCriticaSamuError",
    "Triagem",
    "TriagemInvalidaError",
    "calcular_hash_tcle",
    "classificar_risco_clinico",
]
