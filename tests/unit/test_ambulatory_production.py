"""Unit tests for SUS ambulatory production and eligibility.

Conforme RF-02, RF-05, RT-01 e ADR-012.
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from src.core.errors import TenantInvalidoError
from src.modules.ambulatory import (
    BpaProducaoDTO,
    CaraterAtendimento,
    ConsolidarTeleconsultaCommand,
    ElegibilidadeFalhaEvent,
    ElegibilidadeService,
    LoggingElegibilidadeNotifier,
    RequisicaoElegibilidade,
    ResultadoElegibilidade,
    StatusElegibilidade,
    SusEligibilityAdapter,
    TipoProcedimentoAmbulatorial,
)

from tests.doubles import FakeElegibilidadeNotifier, FakeEligibilityProvider


@pytest.mark.asyncio
async def test_sus_adapter_instant_no_op_approval() -> None:
    """SUS adapter immediately approves attendance without network latency (RT-01)."""
    adapter = SusEligibilityAdapter()

    req = RequisicaoElegibilidade(
        organizacao_id=1,
        atendimento_id=uuid4(),
        paciente_id=uuid4(),
        cpf="12345678901",
        cns="123456789012345",
    )

    resultado = await adapter.verificar_elegibilidade(req)

    assert resultado.aprovado is True
    assert resultado.status == StatusElegibilidade.APROVADO
    assert resultado.codigo_autorizacao == "SUS-ISENTO"
    assert resultado.motivo is None


@pytest.mark.asyncio
async def test_elegibilidade_service_emits_failure_event_on_rejection() -> None:
    """ElegibilidadeService dispatches failure event to waiting room on rejection."""
    provider = FakeEligibilityProvider(
        ResultadoElegibilidade(
            aprovado=False,
            status=StatusElegibilidade.REJEITADO,
            motivo="Cadastro SUS irregular",
        )
    )
    notifier = FakeElegibilidadeNotifier()

    service = ElegibilidadeService(
        provider=provider,
        notifier=notifier,
    )
    atend_id = uuid4()
    pac_id = uuid4()
    req = RequisicaoElegibilidade(
        organizacao_id=1,
        atendimento_id=atend_id,
        paciente_id=pac_id,
    )

    resultado = await service.avaliar_elegibilidade(req)

    assert resultado.aprovado is False
    assert len(notifier.eventos_falha) == 1
    evento = notifier.eventos_falha[0]
    assert evento.atendimento_id == atend_id
    assert evento.paciente_id == pac_id
    assert evento.motivo == "Cadastro SUS irregular"
    assert evento.status == StatusElegibilidade.REJEITADO


@pytest.mark.asyncio
async def test_elegibilidade_service_does_not_notify_on_approval() -> None:
    """ElegibilidadeService does not dispatch failure event when approved."""
    provider = FakeEligibilityProvider(
        ResultadoElegibilidade(
            aprovado=True,
            status=StatusElegibilidade.APROVADO,
            codigo_autorizacao="SUS-ISENTO",
        )
    )
    notifier = FakeElegibilidadeNotifier()

    service = ElegibilidadeService(
        provider=provider,
        notifier=notifier,
    )
    req = RequisicaoElegibilidade(
        organizacao_id=1,
        atendimento_id=uuid4(),
        paciente_id=uuid4(),
    )

    resultado = await service.avaliar_elegibilidade(req)

    assert resultado.aprovado is True
    assert len(notifier.eventos_falha) == 0


@pytest.mark.asyncio
async def test_logging_elegibilidade_notifier(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """LoggingElegibilidadeNotifier logs structured warning."""
    notifier = LoggingElegibilidadeNotifier()
    evento = ElegibilidadeFalhaEvent(
        atendimento_id=uuid4(),
        organizacao_id=1,
        paciente_id=uuid4(),
        motivo="Documento inconsistente",
        status=StatusElegibilidade.REJEITADO,
        disparado_em=datetime.now(UTC),
    )
    with caplog.at_level(logging.WARNING):
        await notifier.notificar_falha(evento)

    assert "Event ELEGIBILIDADE_FALHA" in caplog.text


@pytest.mark.asyncio
async def test_elegibilidade_service_tenant_invalido_raises() -> None:
    service = ElegibilidadeService(
        provider=FakeEligibilityProvider(
            ResultadoElegibilidade(
                aprovado=True,
                status=StatusElegibilidade.APROVADO,
                codigo_autorizacao="SUS-ISENTO",
            )
        )
    )
    req = RequisicaoElegibilidade(
        organizacao_id=0,
        atendimento_id=uuid4(),
        paciente_id=uuid4(),
    )
    match_msg = "Identificador da organização '0' deve ser positivo"
    with pytest.raises(TenantInvalidoError, match=match_msg):
        await service.avaliar_elegibilidade(req)


def test_consolidar_teleconsulta_command_and_bpa_dto() -> None:
    """Verifica contratos tipados para consolidação de faturamento ambulatorial SUS."""
    atend_id = uuid4()
    prof_id = uuid4()
    pac_id = uuid4()
    cnes = "1234567"

    cmd = ConsolidarTeleconsultaCommand(
        atendimento_id=atend_id,
        profissional_id=prof_id,
        paciente_id=pac_id,
        cnes=cnes,
    )

    assert (
        cmd.codigo_sigtap
        == TipoProcedimentoAmbulatorial.CONSULTA_MEDICA_ATENCAO_PRIMARIA
    )
    assert cmd.carater_atendimento == CaraterAtendimento.URGENCIA

    now = datetime.now(UTC)
    bpa = BpaProducaoDTO(
        atendimento_id=atend_id,
        cnes=cnes,
        codigo_sigtap=cmd.codigo_sigtap,
        carater_atendimento=cmd.carater_atendimento,
        consolidado_em=now,
    )

    assert bpa.cnes == "1234567"
    assert bpa.codigo_sigtap == "03.01.01.025-0"
    assert bpa.carater_atendimento == "02"
