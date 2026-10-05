"""Single canonical 64-bit queue score (RN01, ADR-002)."""

from datetime import UTC, datetime

from src.core.errors import ValidationError
from src.modules.queue.domain.models import PrioridadeClinica

SCORE_PRIORITY_MULTIPLIER = 1_000_000_000_000


def calcular_score(
    prioridade_clinica: int | PrioridadeClinica,
    timestamp_epoch: int | float | datetime | None = None,
) -> int:
    prioridade_int = int(prioridade_clinica)
    if prioridade_int < 1 or prioridade_int > 5:
        raise ValidationError(
            "Prioridade clínica deve ser entre 1 e 5 (1=Emergência, 5=Não Urgente)."
        )
    if timestamp_epoch is None:
        ts_segundos = int(datetime.now(UTC).timestamp())
    elif isinstance(timestamp_epoch, datetime):
        ts_segundos = int(timestamp_epoch.timestamp())
    else:
        ts_segundos = int(timestamp_epoch)
    return (prioridade_int * SCORE_PRIORITY_MULTIPLIER) + ts_segundos
