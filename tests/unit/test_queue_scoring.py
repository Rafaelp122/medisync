"""Unit tests for queue domain scoring single source."""

from datetime import UTC, datetime

import pytest
from src.core.errors import ValidationError
from src.modules.queue.domain.scoring import calcular_score


def test_score_formula_prioridade_vezes_1e12_mais_epoch() -> None:
    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    epoch = int(ts.timestamp())
    assert calcular_score(1, ts) == 1_000_000_000_000 + epoch
    assert calcular_score(5, ts) == 5_000_000_000_000 + epoch


def test_score_rejeita_prioridade_fora_1_5() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="entre 1 e 5"):
        calcular_score(0, ts)
    with pytest.raises(ValidationError, match="entre 1 e 5"):
        calcular_score(6, ts)


def test_score_aceita_none_usando_now() -> None:
    antes = int(datetime.now(UTC).timestamp())
    score = calcular_score(3, None)
    depois = int(datetime.now(UTC).timestamp())
    assert 3_000_000_000_000 + antes <= score <= 3_000_000_000_000 + depois
