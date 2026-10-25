"""Unit tests for queue presentation schemas.

Covers US-01, US-06, US-07, and ADR-001/ADR-008.
"""

from datetime import UTC, datetime
from uuid import uuid4

from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoResult,
    AlocacaoChamadaResult,
    PioraClinicaResult,
)
from src.modules.queue.presentation.schemas import (
    AdmissaoResponse,
    ChamarProximoResponse,
    PioraClinicaResponse,
)


def test_admissao_response_model_validate_com_tcle_hash() -> None:
    """Verifica que AdmissaoResponse expõe tcle_hash via model_validate (US-01)."""
    tcle_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    result = AdmissaoAtendimentoResult(
        atendimento_id=uuid4(),
        triagem_id=uuid4(),
        organizacao_id=1,
        paciente_id=uuid4(),
        status_atendimento="TRIADO_AGUARDANDO_ELEGIBILIDADE",
        prioridade_clinica=3,
        alerta_samu_disparado=False,
        instrucoes="Aguarde validação de elegibilidade",
        tcle_hash=tcle_hash,
    )
    resp = AdmissaoResponse.model_validate(result)
    assert resp.tcle_hash == tcle_hash
    assert resp.atendimento_id == result.atendimento_id
    assert resp.prioridade_clinica == 3
    assert resp.status_atendimento == "TRIADO_AGUARDANDO_ELEGIBILIDADE"


def test_piora_clinica_response_campos_canonicos_emergencia() -> None:
    """Verifica contrato de resposta para piora crítica SAMU Nível 1 (US-06)."""
    atend_id = uuid4()
    instrucao_samu = "Ligue imediatamente para o SAMU 192 ou dirija-se à UPA."
    result = PioraClinicaResult(
        atendimento_id=atend_id,
        prioridade_clinica=1,
        alerta_samu_disparado=True,
        redirecionado_emergencia=True,
        nova_posicao=None,
        instrucoes=instrucao_samu,
        nova_prioridade=1,
        status_atendimento="CANCELADO_PELO_PACIENTE",
        orientacoes_emergencia=instrucao_samu,
    )
    resp = PioraClinicaResponse.model_validate(result)
    assert resp.atendimento_id == atend_id
    assert resp.nova_prioridade == 1
    assert resp.status_atendimento == "CANCELADO_PELO_PACIENTE"
    assert resp.alerta_samu_disparado is True
    assert resp.orientacoes_emergencia == instrucao_samu


def test_piora_clinica_response_campos_canonicos_agravamento() -> None:
    """Verifica contrato de resposta para agravamento sem emergência Nível 2 (US-06)."""
    atend_id = uuid4()
    result = PioraClinicaResult(
        atendimento_id=atend_id,
        prioridade_clinica=2,
        alerta_samu_disparado=False,
        redirecionado_emergencia=False,
        nova_posicao=1,
        instrucoes="Prioridade recalculada com sucesso na fila de espera.",
        nova_prioridade=2,
        status_atendimento="APTO_PARA_CHAMADA",
        orientacoes_emergencia=None,
    )
    resp = PioraClinicaResponse.model_validate(result)
    assert resp.atendimento_id == atend_id
    assert resp.nova_prioridade == 2
    assert resp.status_atendimento == "APTO_PARA_CHAMADA"
    assert resp.alerta_samu_disparado is False
    assert resp.nova_posicao == 1
    assert resp.orientacoes_emergencia is None


def test_chamar_proximo_response_model_validate_paciente_e_prioridade() -> None:
    """Verifica que ChamarProximoResponse expõe paciente_id e
    prioridade_clinica (US-07).
    """
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
