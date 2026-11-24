"""Unit tests for queue presentation schemas.

Covers US-01, US-06, US-07, and ADR-001/ADR-008.
"""

from datetime import UTC, datetime
from uuid import uuid4

from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoResult,
    AlocacaoChamadaResult,
    PioraClinicaResult,
    PosicaoFilaResult,
)
from src.modules.queue.presentation.schemas import (
    AdmissaoRequest,
    AdmissaoResponse,
    ChamarProximoResponse,
    PioraClinicaResponse,
    PosicaoFilaResponse,
)


def test_admissao_request_nao_expoe_medicos_ativos() -> None:
    """AdmissaoRequest must not accept client-spoofed medicos_ativos (RN05)."""
    assert "medicos_ativos" not in AdmissaoRequest.model_fields


def test_admissao_response_model_validate_com_tcle_hash() -> None:
    """Verifica que AdmissaoResponse expõe tcle_hash via model_validate (US-01)."""
    tcle_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    result = AdmissaoAtendimentoResult(
        atendimento_id=uuid4(),
        triagem_id=uuid4(),
        paciente_id=uuid4(),
        status_atendimento="APTO_PARA_CHAMADA",
        prioridade_clinica=3,
        alerta_samu_disparado=False,
        instrucoes=None,
        tcle_hash=tcle_hash,
    )
    resp = AdmissaoResponse.model_validate(result)
    assert resp.tcle_hash == tcle_hash
    assert resp.atendimento_id == result.atendimento_id
    assert resp.prioridade_clinica == 3
    assert resp.status_atendimento == "APTO_PARA_CHAMADA"


def test_posicao_fila_response_serializa_timer_e_prioridade() -> None:
    """PosicaoFilaResponse exposes chamada_iniciada_em, ttl_segundos, prioridade."""
    chamada_em = datetime.now(UTC)
    result = PosicaoFilaResult(
        atendimento_id=uuid4(),
        status="CHAMANDO_PACIENTE",
        posicao=0,
        total_aguardando=3,
        tempo_estimado_segundos=0,
        prioridade_clinica=2,
        chamada_iniciada_em=chamada_em,
        ttl_segundos=45,
    )
    resp = PosicaoFilaResponse.model_validate(result)
    assert resp.prioridade_clinica == 2
    assert resp.chamada_iniciada_em == chamada_em
    assert resp.ttl_segundos == 45


def test_piora_clinica_response_campos_canonicos_emergencia() -> None:
    """Verifica contrato canônico sem espelhos para piora crítica SAMU Nível 1."""
    assert "nova_prioridade" not in PioraClinicaResponse.model_fields
    assert "orientacoes_emergencia" not in PioraClinicaResponse.model_fields

    atend_id = uuid4()
    instrucao_samu = "Ligue imediatamente para o SAMU 192 ou dirija-se à UPA."
    result = PioraClinicaResult(
        atendimento_id=atend_id,
        prioridade_clinica=1,
        alerta_samu_disparado=True,
        redirecionado_emergencia=True,
        nova_posicao=None,
        instrucoes=instrucao_samu,
        status_atendimento="CANCELADO_PACIENTE",
    )
    resp = PioraClinicaResponse.model_validate(result)
    assert resp.atendimento_id == atend_id
    assert resp.prioridade_clinica == 1
    assert resp.status_atendimento == "CANCELADO_PACIENTE"
    assert resp.alerta_samu_disparado is True
    assert resp.redirecionado_emergencia is True
    assert resp.instrucoes == instrucao_samu


def test_piora_clinica_response_campos_canonicos_agravamento() -> None:
    """Verifica contrato canônico sem espelhos para agravamento Nível 2."""
    atend_id = uuid4()
    result = PioraClinicaResult(
        atendimento_id=atend_id,
        prioridade_clinica=2,
        alerta_samu_disparado=False,
        redirecionado_emergencia=False,
        nova_posicao=1,
        instrucoes="Prioridade recalculada com sucesso na fila de espera.",
        status_atendimento="APTO_PARA_CHAMADA",
    )
    resp = PioraClinicaResponse.model_validate(result)
    assert resp.atendimento_id == atend_id
    assert resp.prioridade_clinica == 2
    assert resp.status_atendimento == "APTO_PARA_CHAMADA"
    assert resp.alerta_samu_disparado is False
    assert resp.nova_posicao == 1
    assert resp.instrucoes == "Prioridade recalculada com sucesso na fila de espera."


def test_chamar_proximo_response_model_validate_paciente_e_prioridade() -> None:
    """Verifica que ChamarProximoResponse expõe paciente_id e prioridade_clinica."""
    atend_id = uuid4()
    medico_id = uuid4()
    paciente_id = uuid4()
    agora = datetime.now(UTC)

    result = AlocacaoChamadaResult(
        atendimento_id=atend_id,
        medico_id=medico_id,
        status="CHAMANDO_PACIENTE",
        chamada_iniciada_em=agora,
        ttl_segundos=45,
        paciente_id=paciente_id,
        prioridade_clinica=2,
        alocado=True,
        mensagem="Paciente alocado com sucesso para chamada.",
    )
    resp = ChamarProximoResponse.model_validate(result)
    assert resp.alocado is True
    assert resp.atendimento_id == atend_id
    assert resp.medico_id == medico_id
    assert resp.paciente_id == paciente_id
    assert resp.prioridade_clinica == 2
    assert resp.status == "CHAMANDO_PACIENTE"
    assert resp.ttl_segundos == 45
    assert resp.mensagem == "Paciente alocado com sucesso para chamada."
