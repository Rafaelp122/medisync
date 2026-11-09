"""Unit tests for Clinical AI Governance under CFM nº 2.454/2026 and SIGTAP codes."""

from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from src.core.audit import AtorPapel, AtorTipo
from src.core.errors import IANaoRatificadaError
from src.modules.consultation.application.dtos import RegistrarEvolucaoSOAPCommand
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoResumoDTO,
)
from src.modules.consultation.application.services.evolucao_service import (
    EvolucaoService,
)
from src.modules.consultation.domain.models import EvolucaoClinica

from tests.doubles import FakeAsyncSession, FakeAuditTrail, FakeResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _make_resumo_nao_terminal(atendimento_id: UUID) -> AtendimentoResumoDTO:
    return AtendimentoResumoDTO(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=uuid4(),
        status="EM_ATENDIMENTO",
        tcle_hash="a" * 64,
        is_terminal=False,
    )


@pytest.mark.asyncio
async def test_evolucao_rejeita_ia_nao_ratificada() -> None:
    session = AsyncMock()
    reader = AsyncMock()
    atendimento_id = uuid4()
    medico_id = uuid4()
    reader.obter_resumo.return_value = _make_resumo_nao_terminal(atendimento_id)

    svc = EvolucaoService(session=session, reader=reader)

    cmd = RegistrarEvolucaoSOAPCommand(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=medico_id,
        anamnese="Paciente com cefaleia há 2 dias",
        conduta="Prescrever dipirona 1g de 6/6h se dor",
        ia_utilizada=True,
        ia_modelo="gemini-1.5-pro",
        ia_sugestao_bruta="Prescrever paracetamol 500mg",
        ia_ratificada_pelo_medico=False,
    )

    with pytest.raises(IANaoRatificadaError) as exc_info:
        await svc.salvar_evolucao_soap(cmd)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "IA_NAO_RATIFICADA"
    assert "não foi ratificada pelo médico assistente" in str(exc_info.value)
    assert str(medico_id) in str(exc_info.value)


@pytest.mark.asyncio
async def test_evolucao_aceita_ia_ratificada_com_diff_automatico() -> None:
    session = FakeAsyncSession(results=[FakeResult(None)])
    reader = AsyncMock()
    atendimento_id = uuid4()
    medico_id = uuid4()
    reader.obter_resumo.return_value = _make_resumo_nao_terminal(atendimento_id)
    fake_audit = FakeAuditTrail()

    svc = EvolucaoService(
        session=cast("AsyncSession", session),
        reader=reader,
        audit_trail=fake_audit,
    )

    sugestao_bruta = "Conduta sugerida: Repouso e hidratação oral."
    conduta_final = (
        "Conduta sugerida: Repouso, hidratação oral vigorosa e retorno se febre."
    )

    cmd = RegistrarEvolucaoSOAPCommand(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=medico_id,
        anamnese="Sintomas gripais leves",
        conduta=conduta_final,
        ia_utilizada=True,
        ia_modelo="clinical-assist-v1",
        ia_sugestao_bruta=sugestao_bruta,
        ia_diff_modificacao=None,
        ia_ratificada_pelo_medico=True,
    )

    evolucao = await svc.salvar_evolucao_soap(cmd)

    assert evolucao.ia_utilizada is True
    assert evolucao.ia_modelo == "clinical-assist-v1"
    assert evolucao.ia_ratificada_pelo_medico is True
    assert evolucao.ia_diff_modificacao is not None
    assert "--- sugestao_ia" in evolucao.ia_diff_modificacao
    assert "+++ plano_ratificado" in evolucao.ia_diff_modificacao
    assert evolucao.codigo_sigtap == "03.01.01.025-0"

    # Verificação de registro forense na trilha de auditoria (CFM nº 2.454/2026)
    events = fake_audit.get_events_by_type("IA_DECISAO_MEDICA_REGISTRADA")
    assert len(events) == 1
    evt = events[0]
    assert evt["organizacao_id"] == 1
    assert evt["atendimento_id"] == atendimento_id
    assert evt["ator_tipo"] == AtorTipo.PROFISSIONAL.value
    assert evt["ator_papel"] == AtorPapel.MEDICO.value
    assert evt["ator_id"] == medico_id
    assert evt["payload"]["evolucao_id"] == str(evolucao.id)
    assert evt["payload"]["ia_modelo"] == "clinical-assist-v1"
    assert evt["payload"]["ia_ratificada"] is True
    assert evt["payload"]["diff_forense"] == evolucao.ia_diff_modificacao
    assert "--- sugestao_ia" in evt["payload"]["diff_forense"]
    assert "+++ plano_ratificado" in evt["payload"]["diff_forense"]


@pytest.mark.asyncio
async def test_evolucao_update_com_ia_registra_evento_auditoria() -> None:
    atendimento_id = uuid4()
    medico_id = uuid4()
    existing = EvolucaoClinica(
        organizacao_id=1,
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        anamnese="Anamnese inicial",
        conduta="Conduta inicial",
    )
    session = FakeAsyncSession(results=[FakeResult(existing)])
    reader = AsyncMock()
    reader.obter_resumo.return_value = _make_resumo_nao_terminal(atendimento_id)
    fake_audit = FakeAuditTrail()

    svc = EvolucaoService(
        session=cast("AsyncSession", session),
        reader=reader,
        audit_trail=fake_audit,
    )

    cmd = RegistrarEvolucaoSOAPCommand(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=medico_id,
        anamnese="Anamnese atualizada",
        conduta="Prescrição ajustada com IA",
        ia_utilizada=True,
        ia_modelo="gemini-2.0-flash",
        ia_sugestao_bruta="Prescrição sugerida pela IA",
        ia_ratificada_pelo_medico=True,
    )

    evolucao = await svc.salvar_evolucao_soap(cmd)
    assert evolucao.id == existing.id

    ia_events = fake_audit.get_events_by_type("IA_DECISAO_MEDICA_REGISTRADA")
    assert len(ia_events) == 1
    evt = ia_events[0]
    assert evt["payload"]["evolucao_id"] == str(existing.id)
    assert evt["payload"]["ia_modelo"] == "gemini-2.0-flash"
    assert evt["payload"]["ia_ratificada"] is True
    assert evt["payload"]["diff_forense"] is not None
    assert evt["payload"]["diff_forense"] == evolucao.ia_diff_modificacao
    assert "--- sugestao_ia" in evt["payload"]["diff_forense"]
    assert "+++ plano_ratificado" in evt["payload"]["diff_forense"]


@pytest.mark.asyncio
async def test_evolucao_persiste_codigo_sigtap_customizado() -> None:
    session = FakeAsyncSession(results=[FakeResult(None)])
    reader = AsyncMock()
    atendimento_id = uuid4()
    medico_id = uuid4()
    reader.obter_resumo.return_value = _make_resumo_nao_terminal(atendimento_id)
    fake_audit = FakeAuditTrail()

    svc = EvolucaoService(
        session=cast("AsyncSession", session),
        reader=reader,
        audit_trail=fake_audit,
    )

    cmd = RegistrarEvolucaoSOAPCommand(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=medico_id,
        anamnese="Consulta especializada",
        conduta="Encaminhamento ambulatorial",
        codigo_sigtap="03.01.01.004-8",
        ia_utilizada=False,
    )

    evolucao = await svc.salvar_evolucao_soap(cmd)

    assert evolucao.codigo_sigtap == "03.01.01.004-8"
    assert evolucao.ia_utilizada is False
    assert evolucao.ia_diff_modificacao is None
    assert len(fake_audit.get_events_by_type("IA_DECISAO_MEDICA_REGISTRADA")) == 0
