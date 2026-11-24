"""Unit tests for atomic daily admission quota and rollback (RN05 / NC-QUE-01)."""

from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.queue.application.dtos import AdmissaoAtendimentoCommand
from src.modules.queue.application.ports.shift_policy_reader_port import ShiftPolicyDTO
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import AdmissaoFilaSuspensaError
from src.modules.triage.application.services.triage_service import TriageService

from tests.doubles import (
    FakeAsyncSession,
    FakeEmergencyNotifier,
    FakeQueueEngine,
    FakeShiftPolicyReader,
)


@pytest.mark.asyncio
async def test_admissao_reserva_cota_diaria_atomica_e_insere_zset_pos_commit() -> None:
    """admitir_paciente increments daily quota atomically and ingests post-commit."""
    engine = FakeQueueEngine(medicos_ativos={uuid4(), uuid4()}, cota_diaria_usada=10)
    session = FakeAsyncSession()
    triage = TriageService(
        session=cast("AsyncSession", session),
        emergency_notifier=FakeEmergencyNotifier(),
    )
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        triage_port=triage,
        shift_policy_reader=FakeShiftPolicyReader(
            ShiftPolicyDTO(cota_diaria_maxima=300)
        ),
    )

    cmd = AdmissaoAtendimentoCommand(
        paciente_id=uuid4(),
        queixa_principal="Febre baixa há 1 dia",
        sintomas=["febre"],
        tcle_texto="Consentimento para teleconsulta",
    )

    result = await service.admitir_paciente(cmd)
    assert result.paciente_id == cmd.paciente_id
    assert engine.cota_diaria_usada == 11
    assert session.commits == 1
    assert result.atendimento_id in engine.fila_scores


@pytest.mark.asyncio
async def test_admissao_bloqueada_quando_cota_diaria_atingida() -> None:
    """When daily cap is reached, atomic reservation fails without DB write."""
    engine = FakeQueueEngine(medicos_ativos={uuid4(), uuid4()}, cota_diaria_usada=300)
    session = FakeAsyncSession()
    triage = TriageService(
        session=cast("AsyncSession", session),
        emergency_notifier=FakeEmergencyNotifier(),
    )
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        triage_port=triage,
        shift_policy_reader=FakeShiftPolicyReader(
            ShiftPolicyDTO(cota_diaria_maxima=300)
        ),
    )

    cmd = AdmissaoAtendimentoCommand(
        paciente_id=uuid4(),
        queixa_principal="Cansaço leve",
        sintomas=[],
        tcle_texto="Consentimento para teleconsulta",
    )

    with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
        await service.admitir_paciente(cmd)

    assert exc_info.value.motivo == "COTA_ATINGIDA"
    assert engine.cota_diaria_usada == 300
    assert session.commits == 0
    assert len(engine.fila_scores) == 0


@pytest.mark.asyncio
async def test_admissao_estorna_cota_diaria_em_falha_commit() -> None:
    """DB failure on commit rolls back reserved daily quota (DECR) and skips ZSET."""
    engine = FakeQueueEngine(medicos_ativos={uuid4(), uuid4()}, cota_diaria_usada=42)
    session = FakeAsyncSession(commit_error=RuntimeError("Postgres deadlock"))
    triage = TriageService(
        session=cast("AsyncSession", session),
        emergency_notifier=FakeEmergencyNotifier(),
    )
    service = FilaService(
        queue_engine=engine,
        db_session=cast("AsyncSession", session),
        triage_port=triage,
        shift_policy_reader=FakeShiftPolicyReader(
            ShiftPolicyDTO(cota_diaria_maxima=300)
        ),
    )

    cmd = AdmissaoAtendimentoCommand(
        paciente_id=uuid4(),
        queixa_principal="Dor de garganta leve",
        sintomas=["odinofagia"],
        tcle_texto="Consentimento válido",
    )

    with pytest.raises(RuntimeError, match="Postgres deadlock"):
        await service.admitir_paciente(cmd)

    assert session.rollbacks == 1
    assert engine.cota_diaria_usada == 42
    assert len(engine.fila_scores) == 0
