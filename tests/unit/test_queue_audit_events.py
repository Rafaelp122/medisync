"""Unit tests for clinical audit trail integration in the queue module (ADR-007).

Decisões: docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md
Referência: docs/reference/audit/event-catalog.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AtorPapel, AtorTipo
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AlocarChamadaCommand,
    PioraClinicaCommand,
)
from src.modules.queue.application.ports.allocation_port import (
    AlocacaoCodigo,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)

from tests.doubles import FakeAsyncSession, FakeAuditTrail, FakeValkey


@dataclass
class DummyTriageEvaluation:
    prioridade_clinica: int
    alerta_samu_disparado: bool = False
    tcle_hash: str = ""
    tcle_texto: str = ""
    instrucao_redirecionamento: str | None = None


@pytest.fixture
def fake_valkey() -> FakeValkey:
    return FakeValkey()


@pytest.fixture
def fake_audit_trail() -> FakeAuditTrail:
    return FakeAuditTrail()


@pytest.mark.asyncio
async def test_admitir_paciente_records_admissao_audit_event(
    fake_valkey: FakeValkey,
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    paciente_id = uuid4()
    tcle_hash = "f" * 64

    fake_session = FakeAsyncSession()
    mock_triage = MagicMock()
    mock_triage.avaliar_risco = AsyncMock(
        return_value=DummyTriageEvaluation(
            prioridade_clinica=PrioridadeClinica.POUCO_URGENTE,
            alerta_samu_disparado=False,
            tcle_hash=tcle_hash,
            tcle_texto="Termo de Consentimento Livre e Esclarecido",
        )
    )
    mock_triage.registrar_triagem = AsyncMock(return_value=uuid4())

    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("AsyncSession", fake_session),
        triage_port=mock_triage,
        audit_trail=fake_audit_trail,
    )

    cmd = AdmissaoAtendimentoCommand(
        organizacao_id=org_id,
        paciente_id=paciente_id,
        queixa_principal="Dor de garganta leve",
        sintomas=["dor_garganta", "febre_baixa"],
        escala_dor=3,
        tcle_texto="Termo de Consentimento Livre e Esclarecido",
        tcle_hash=tcle_hash,
    )

    result = await fila_service.admitir_paciente(cmd)
    assert (
        result.status_atendimento
        == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
    )

    events = fake_audit_trail.get_events_by_type("ADMISSAO_PACIENTE")
    assert len(events) == 1
    evt = events[0]
    assert evt["organizacao_id"] == org_id
    assert evt["ator_tipo"] == AtorTipo.PACIENTE.value
    assert evt["ator_papel"] == AtorPapel.PACIENTE.value
    assert evt["ator_id"] == paciente_id
    assert evt["tcle_hash"] == tcle_hash
    assert evt["novo_estado"] == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
    assert evt["payload"]["prioridade_clinica"] == PrioridadeClinica.POUCO_URGENTE


@pytest.mark.asyncio
async def test_admitir_atendimento_apto_records_elegibilidade_confirmada_audit_event(
    fake_valkey: FakeValkey,
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    atendimento_id = uuid4()
    paciente_id = uuid4()
    atendimento = Atendimento(
        id=atendimento_id,
        organizacao_id=org_id,
        paciente_id=paciente_id,
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="b" * 64,
    )
    fake_session = FakeAsyncSession(entities={atendimento_id: atendimento})

    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("AsyncSession", fake_session),
        audit_trail=fake_audit_trail,
    )

    res = await fila_service.admitir_atendimento_apto(org_id, atendimento_id)
    assert res.promovido is True

    events = fake_audit_trail.get_events_by_type("ELEGIBILIDADE_CONFIRMADA")
    assert len(events) == 1
    evt = events[0]
    assert evt["organizacao_id"] == org_id
    assert evt["atendimento_id"] == atendimento_id
    assert evt["ator_tipo"] == AtorTipo.SISTEMA.value
    assert evt["ator_papel"] == AtorPapel.WORKER_ARQ.value
    assert evt["ator_id"] is None
    assert (
        evt["estado_anterior"]
        == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
    )

    assert evt["novo_estado"] == StatusAtendimento.APTO_PARA_CHAMADA.value


@pytest.mark.asyncio
async def test_alocar_chamada_records_chamada_iniciada_audit_event(
    fake_valkey: FakeValkey,
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    atendimento_id = uuid4()
    medico_id = uuid4()
    atendimento = Atendimento(
        id=atendimento_id,
        organizacao_id=org_id,
        paciente_id=uuid4(),
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="c" * 64,
    )
    fake_session = FakeAsyncSession(entities={atendimento_id: atendimento})

    mock_lua = MagicMock()
    mock_lua.alocar_chamada = AsyncMock(return_value=AlocacaoCodigo.SUCESSO)

    alocacao_service = AlocacaoChamadaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("AsyncSession", fake_session),
        lua_manager=mock_lua,
        audit_trail=fake_audit_trail,
    )

    cmd = AlocarChamadaCommand(
        organizacao_id=org_id,
        medico_id=medico_id,
        atendimento_id=atendimento_id,
        ttl_segundos=45,
    )

    await alocacao_service.alocar_chamada(cmd)

    events = fake_audit_trail.get_events_by_type("CHAMADA_INICIADA")
    assert len(events) == 1
    evt = events[0]
    assert evt["organizacao_id"] == org_id
    assert evt["atendimento_id"] == atendimento_id
    assert evt["ator_tipo"] == AtorTipo.PROFISSIONAL.value
    assert evt["ator_papel"] == AtorPapel.MEDICO.value
    assert evt["ator_id"] == medico_id
    assert evt["estado_anterior"] == StatusAtendimento.APTO_PARA_CHAMADA.value
    assert evt["novo_estado"] == StatusAtendimento.CHAMANDO_PACIENTE.value
    assert evt["payload"]["ring_timeout_segundos"] == 45


@pytest.mark.asyncio
async def test_atender_chamada_records_chamada_atendida_audit_event(
    fake_valkey: FakeValkey,
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    atendimento_id = uuid4()
    paciente_id = uuid4()
    medico_id = uuid4()
    atendimento = Atendimento(
        id=atendimento_id,
        organizacao_id=org_id,
        paciente_id=paciente_id,
        medico_id=medico_id,
        status=StatusAtendimento.CHAMANDO_PACIENTE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="d" * 64,
    )
    fake_session = FakeAsyncSession(entities={atendimento_id: atendimento})

    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("AsyncSession", fake_session),
        audit_trail=fake_audit_trail,
    )

    await fila_service.atender_chamada(atendimento_id)

    assert atendimento.status == StatusAtendimento.EM_ATENDIMENTO.value

    events = fake_audit_trail.get_events_by_type("CHAMADA_ATENDIDA")
    assert len(events) == 1
    evt = events[0]
    assert evt["ator_tipo"] == AtorTipo.PACIENTE.value
    assert evt["ator_papel"] == AtorPapel.PACIENTE.value
    assert evt["ator_id"] == paciente_id
    assert evt["estado_anterior"] == StatusAtendimento.CHAMANDO_PACIENTE.value
    assert evt["novo_estado"] == StatusAtendimento.EM_ATENDIMENTO.value


@pytest.mark.asyncio
async def test_resolver_ring_timeout_records_timeout_no_show_audit_event(
    fake_valkey: FakeValkey,
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    atendimento_id = uuid4()
    medico_id = uuid4()
    atendimento = Atendimento(
        id=atendimento_id,
        organizacao_id=org_id,
        paciente_id=uuid4(),
        medico_id=medico_id,
        status=StatusAtendimento.CHAMANDO_PACIENTE,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="e" * 64,
    )
    fake_session = FakeAsyncSession(entities={atendimento_id: atendimento})

    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("AsyncSession", fake_session),
        audit_trail=fake_audit_trail,
    )

    res = await fila_service.resolver_ring_timeout(org_id, atendimento_id, medico_id)
    assert res == "no_show_recorded"

    assert atendimento.status == StatusAtendimento.PACIENTE_AUSENTE.value

    events = fake_audit_trail.get_events_by_type("TIMEOUT_CHAMADA_NO_SHOW")
    assert len(events) == 1
    evt = events[0]
    assert evt["ator_tipo"] == AtorTipo.SISTEMA.value
    assert evt["ator_papel"] == AtorPapel.WORKER_ARQ.value
    assert evt["novo_estado"] == StatusAtendimento.PACIENTE_AUSENTE.value


@pytest.mark.asyncio
async def test_cancelar_atendimento_paciente_records_cancelamento_audit_event(
    fake_valkey: FakeValkey,
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    atendimento_id = uuid4()
    paciente_id = uuid4()
    atendimento = Atendimento(
        id=atendimento_id,
        organizacao_id=org_id,
        paciente_id=paciente_id,
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash="a" * 64,
    )
    fake_session = FakeAsyncSession(entities={atendimento_id: atendimento})

    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("AsyncSession", fake_session),
        audit_trail=fake_audit_trail,
    )

    await fila_service.cancelar_atendimento_paciente(
        org_id, atendimento_id, motivo="Desistência voluntária"
    )
    assert atendimento.status == StatusAtendimento.CANCELADO_PACIENTE.value

    events = fake_audit_trail.get_events_by_type("ATENDIMENTO_CANCELADO_PACIENTE")
    assert len(events) == 1
    evt = events[0]
    assert evt["ator_tipo"] == AtorTipo.PACIENTE.value
    assert evt["ator_papel"] == AtorPapel.PACIENTE.value
    assert evt["ator_id"] == paciente_id
    assert evt["payload"]["motivo"] == "Desistência voluntária"


@pytest.mark.asyncio
async def test_processar_piora_clinica_samu_records_deterioracao_audit_event(
    fake_valkey: FakeValkey,
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    atendimento_id = uuid4()
    paciente_id = uuid4()
    atendimento = Atendimento(
        id=atendimento_id,
        organizacao_id=org_id,
        paciente_id=paciente_id,
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=PrioridadeClinica.POUCO_URGENTE,
        tcle_hash="9" * 64,
    )
    fake_session = FakeAsyncSession(entities={atendimento_id: atendimento})

    mock_triage = MagicMock()
    mock_triage.avaliar_risco = AsyncMock(
        return_value=DummyTriageEvaluation(
            prioridade_clinica=1,
            alerta_samu_disparado=True,
            tcle_hash="9" * 64,
            tcle_texto="Termo",
            instrucao_redirecionamento="SAMU 192",
        )
    )

    fila_service = FilaService(
        valkey=cast("Any", fake_valkey),
        db_session=cast("AsyncSession", fake_session),
        triage_port=mock_triage,
        audit_trail=fake_audit_trail,
    )

    cmd = PioraClinicaCommand(
        organizacao_id=org_id,
        atendimento_id=atendimento_id,
        queixa_adicional="Dor no peito irradiando para o braço",
        novos_sintomas=["dor_toracica", "sudorese"],
        escala_dor=10,
    )

    res = await fila_service.processar_piora_clinica(cmd)
    assert res.alerta_samu_disparado is True
    assert atendimento.status == StatusAtendimento.CANCELADO_PACIENTE.value

    events = fake_audit_trail.get_events_by_type("PIORA_CLINICA_REGISTRADA")
    assert len(events) == 1
    evt = events[0]
    assert evt["ator_tipo"] == AtorTipo.PACIENTE.value
    assert evt["ator_papel"] == AtorPapel.PACIENTE.value
    assert evt["ator_id"] == paciente_id
    assert evt["novo_estado"] == StatusAtendimento.CANCELADO_PACIENTE.value
    assert evt["payload"]["alerta_samu"] is True
