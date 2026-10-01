"""Unit tests for Atendimento domain model and state machine (RN03)."""

from datetime import UTC, datetime, timedelta
from enum import IntEnum, StrEnum
from uuid import UUID

import pytest
from src.core.errors import DomainError, ValidationError
from src.core.uuid7 import uuid7
from src.modules.queue.domain.exceptions import TransicaoEstadoInvalidaError
from src.modules.queue.domain.models.atendimento import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)

SAMPLE_TCLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ANOTHER_TCLE_HASH = "a" * 64


def test_status_atendimento_enum_values() -> None:
    assert issubclass(StatusAtendimento, StrEnum)
    expected = {
        "TRIADO_AGUARDANDO_ELEGIBILIDADE",
        "APTO_PARA_CHAMADA",
        "CHAMANDO_PACIENTE",
        "EM_ATENDIMENTO",
        "PACIENTE_AUSENTE",
        "CONCLUIDO",
        "CANCELADO_PACIENTE",
    }
    assert {s.value for s in StatusAtendimento} == expected


def test_prioridade_clinica_enum_values() -> None:
    assert issubclass(PrioridadeClinica, IntEnum)
    assert PrioridadeClinica.EMERGENCIA == 1
    assert PrioridadeClinica.MUITO_URGENTE == 2
    assert PrioridadeClinica.URGENTE == 3
    assert PrioridadeClinica.POUCO_URGENTE == 4
    assert PrioridadeClinica.NAO_URGENTE == 5


def test_transicao_estado_invalida_error_attributes() -> None:
    err = TransicaoEstadoInvalidaError("Transição não permitida.")
    assert isinstance(err, DomainError)
    assert err.status_code == 409
    assert err.code == "TRANSICAO_ESTADO_INVALIDA"


def test_criar_atendimento_defaults() -> None:
    paciente_id = uuid7()
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=paciente_id,
        tcle_hash=SAMPLE_TCLE_HASH,
    )

    assert isinstance(atendimento.id, UUID)
    assert atendimento.organizacao_id == 1
    assert atendimento.paciente_id == paciente_id
    assert atendimento.medico_id is None
    assert atendimento.status == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE
    assert atendimento.prioridade_clinica == PrioridadeClinica.NAO_URGENTE
    assert atendimento.tcle_hash == SAMPLE_TCLE_HASH
    assert atendimento.data_entrada_fila is None
    assert atendimento.chamada_iniciada_em is None
    assert atendimento.chamada_finalizada_em is None
    assert atendimento.is_em_fila is True
    assert atendimento.is_apto_para_chamada is False
    assert atendimento.is_chamando is False
    assert atendimento.is_em_atendimento is False
    assert atendimento.is_ativo is True
    assert atendimento.is_finalizado is False
    assert atendimento.tempo_espera_segundos is None
    assert atendimento.duracao_chamada_segundos is None


def test_criar_atendimento_validacoes_iniciais() -> None:
    paciente_id = uuid7()

    with pytest.raises(ValidationError, match="organizacao_id inválido"):
        Atendimento(organizacao_id=0, paciente_id=paciente_id)

    with pytest.raises(
        ValidationError, match="Prioridade clínica deve ser entre 1 e 5"
    ):
        Atendimento(
            organizacao_id=1,
            paciente_id=paciente_id,
            prioridade_clinica=0,
        )

    with pytest.raises(
        ValidationError, match="Prioridade clínica deve ser entre 1 e 5"
    ):
        Atendimento(
            organizacao_id=1,
            paciente_id=paciente_id,
            prioridade_clinica=6,
        )


def test_tcle_hash_validacao_e_imutabilidade() -> None:
    paciente_id = uuid7()

    with pytest.raises(ValidationError, match="Hash do TCLE inválido"):
        Atendimento(
            organizacao_id=1,
            paciente_id=paciente_id,
            tcle_hash="hash_invalido",
        )

    atendimento = Atendimento(organizacao_id=1, paciente_id=paciente_id)
    assert atendimento.tcle_hash is None

    # Registrar TCLE
    atendimento.registrar_tcle(SAMPLE_TCLE_HASH.upper())
    assert atendimento.tcle_hash == SAMPLE_TCLE_HASH.lower()

    # Re-tentar registrar TCLE (imutabilidade forense - RN07)
    with pytest.raises(ValidationError, match="TCLE já registrado"):
        atendimento.registrar_tcle(ANOTHER_TCLE_HASH)


def test_promover_para_apto_sem_tcle_falha() -> None:
    atendimento = Atendimento(organizacao_id=1, paciente_id=uuid7())
    with pytest.raises(
        ValidationError, match="não pode ser promovido para apto sem consentimento"
    ):
        atendimento.promover_para_apto()


def test_ciclo_vida_completo_happy_path() -> None:
    medico_id = uuid7()
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=uuid7(),
        tcle_hash=SAMPLE_TCLE_HASH,
        prioridade_clinica=PrioridadeClinica.URGENTE,
    )

    # 1. Triado -> Apto para chamada
    atendimento.promover_para_apto()
    assert atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA
    assert atendimento.data_entrada_fila is not None
    assert atendimento.is_em_fila is True
    assert atendimento.is_apto_para_chamada is True

    # 2. Apto para chamada -> Chamando paciente
    atendimento.iniciar_chamada(medico_id=medico_id)
    assert atendimento.status == StatusAtendimento.CHAMANDO_PACIENTE
    assert atendimento.medico_id == medico_id
    assert atendimento.chamada_iniciada_em is not None
    assert atendimento.is_em_fila is False
    assert atendimento.is_chamando is True
    assert atendimento.is_ativo is True

    # 3. Chamando paciente -> Em atendimento
    atendimento.atender_chamada()
    assert atendimento.status == StatusAtendimento.EM_ATENDIMENTO
    assert atendimento.is_em_atendimento is True
    assert atendimento.is_ativo is True
    assert atendimento.is_finalizado is False

    # 4. Em atendimento -> Concluído
    atendimento.concluir_atendimento()
    assert atendimento.status == StatusAtendimento.CONCLUIDO
    assert atendimento.chamada_finalizada_em is not None
    assert atendimento.is_ativo is False
    assert atendimento.is_finalizado is True
    assert atendimento.duracao_chamada_segundos is not None
    assert atendimento.duracao_chamada_segundos >= 0.0
    assert atendimento.tempo_espera_segundos is not None
    assert atendimento.tempo_espera_segundos >= 0.0


def test_iniciar_chamada_sem_medico_falha() -> None:
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=uuid7(),
        tcle_hash=SAMPLE_TCLE_HASH,
    )
    atendimento.promover_para_apto()

    with pytest.raises(ValidationError, match="Médico responsável é obrigatório"):
        atendimento.iniciar_chamada(medico_id=None)  # pyright: ignore[reportArgumentType]


def test_transicoes_ilegais_bloqueadas() -> None:
    medico_id = uuid7()
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=uuid7(),
        tcle_hash=SAMPLE_TCLE_HASH,
    )

    # Tentar chamar direto da triagem (sem estar apto)
    with pytest.raises(
        TransicaoEstadoInvalidaError, match="Apenas atendimentos em 'APTO_PARA_CHAMADA'"
    ):
        atendimento.iniciar_chamada(medico_id=medico_id)

    # Tentar atender chamada direto da triagem
    with pytest.raises(TransicaoEstadoInvalidaError, match="Apenas atendimentos em"):
        atendimento.atender_chamada()

    # Tentar concluir direto da triagem
    with pytest.raises(
        TransicaoEstadoInvalidaError, match="Apenas atendimentos no estado"
    ):
        atendimento.concluir_atendimento()

    # Tentar registrar ausência direto da triagem
    with pytest.raises(TransicaoEstadoInvalidaError, match="Apenas chamadas ativas em"):
        atendimento.registrar_ausencia_paciente()

    # Avançar para apto
    atendimento.promover_para_apto()

    # Tentar promover novamente
    with pytest.raises(TransicaoEstadoInvalidaError, match="Apenas atendimentos em"):
        atendimento.promover_para_apto()

    # Tentar atender sem chamar primeiro
    with pytest.raises(TransicaoEstadoInvalidaError):
        atendimento.atender_chamada()

    # Avançar para chamada
    atendimento.iniciar_chamada(medico_id=medico_id)

    # Tentar concluir enquanto chamando
    with pytest.raises(TransicaoEstadoInvalidaError):
        atendimento.concluir_atendimento()

    # Avançar para em atendimento
    atendimento.atender_chamada()

    # Tentar registrar ausência quando já em atendimento
    with pytest.raises(TransicaoEstadoInvalidaError):
        atendimento.registrar_ausencia_paciente()


def test_resolucao_no_show_ring_timeout() -> None:
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=uuid7(),
        tcle_hash=SAMPLE_TCLE_HASH,
    )
    atendimento.promover_para_apto()
    atendimento.iniciar_chamada(medico_id=uuid7())

    # Ring timeout de 45 segundos expira sem o paciente conectar
    atendimento.registrar_ausencia_paciente()

    assert atendimento.status == StatusAtendimento.PACIENTE_AUSENTE
    assert atendimento.chamada_finalizada_em is not None
    assert atendimento.is_finalizado is True
    assert atendimento.is_ativo is False


def test_cancelamento_pelo_paciente() -> None:
    # 1. Cancelamento na triagem
    a1 = Atendimento(organizacao_id=1, paciente_id=uuid7())
    a1.cancelar_pelo_paciente(motivo="Desistência voluntária")
    assert a1.status == StatusAtendimento.CANCELADO_PACIENTE
    assert a1.is_finalizado is True

    # 2. Cancelamento enquanto apto na fila
    a2 = Atendimento(organizacao_id=1, paciente_id=uuid7(), tcle_hash=SAMPLE_TCLE_HASH)
    a2.promover_para_apto()
    a2.cancelar_pelo_paciente()
    assert a2.status == StatusAtendimento.CANCELADO_PACIENTE

    # 3. Cancelamento durante toque/chamada
    a3 = Atendimento(organizacao_id=1, paciente_id=uuid7(), tcle_hash=SAMPLE_TCLE_HASH)
    a3.promover_para_apto()
    a3.iniciar_chamada(medico_id=uuid7())
    a3.cancelar_pelo_paciente()
    assert a3.status == StatusAtendimento.CANCELADO_PACIENTE
    assert a3.chamada_finalizada_em is not None

    # 4. Proibição de cancelamento após início da teleconsulta clínica
    a4 = Atendimento(organizacao_id=1, paciente_id=uuid7(), tcle_hash=SAMPLE_TCLE_HASH)
    a4.promover_para_apto()
    a4.iniciar_chamada(medico_id=uuid7())
    a4.atender_chamada()
    with pytest.raises(
        TransicaoEstadoInvalidaError,
        match="Não é possível cancelar atendimento já em andamento clínico",
    ):
        a4.cancelar_pelo_paciente()

    # 5. Estado desconhecido / não permitido
    a5 = Atendimento(organizacao_id=1, paciente_id=uuid7())
    a5.status = "ESTADO_DESCONHECIDO"
    with pytest.raises(
        TransicaoEstadoInvalidaError,
        match="não permite cancelamento pelo paciente",
    ):
        a5.cancelar_pelo_paciente()


def test_estados_terminais_bloqueiam_transicoes() -> None:
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=uuid7(),
        tcle_hash=SAMPLE_TCLE_HASH,
    )
    atendimento.promover_para_apto()
    atendimento.iniciar_chamada(medico_id=uuid7())
    atendimento.atender_chamada()
    atendimento.concluir_atendimento()

    medico_id = uuid7()
    with pytest.raises(TransicaoEstadoInvalidaError, match="Atendimento já finalizado"):
        atendimento.promover_para_apto()

    with pytest.raises(TransicaoEstadoInvalidaError, match="Atendimento já finalizado"):
        atendimento.iniciar_chamada(medico_id)

    with pytest.raises(TransicaoEstadoInvalidaError, match="Atendimento já finalizado"):
        atendimento.atender_chamada()

    with pytest.raises(TransicaoEstadoInvalidaError, match="Atendimento já finalizado"):
        atendimento.concluir_atendimento()

    with pytest.raises(TransicaoEstadoInvalidaError, match="Atendimento já finalizado"):
        atendimento.registrar_ausencia_paciente()

    with pytest.raises(TransicaoEstadoInvalidaError, match="Atendimento já finalizado"):
        atendimento.cancelar_pelo_paciente()

    with pytest.raises(TransicaoEstadoInvalidaError, match="Atendimento já finalizado"):
        atendimento.atualizar_prioridade(PrioridadeClinica.EMERGENCIA)


def test_atualizacao_de_prioridade_clinica_medica() -> None:
    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=uuid7(),
        prioridade_clinica=PrioridadeClinica.POUCO_URGENTE,
    )
    assert atendimento.prioridade_clinica == 4

    atendimento.atualizar_prioridade(PrioridadeClinica.MUITO_URGENTE)
    assert atendimento.prioridade_clinica == 2

    atendimento.atualizar_prioridade(1)
    assert atendimento.prioridade_clinica == 1

    with pytest.raises(
        ValidationError, match="Prioridade clínica deve ser entre 1 e 5"
    ):
        atendimento.atualizar_prioridade(9)


def test_calcular_score_fila_valkey() -> None:
    entrada = datetime(2026, 10, 1, 14, 0, 0, tzinfo=UTC)
    epoch = int(entrada.timestamp())

    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=uuid7(),
        tcle_hash=SAMPLE_TCLE_HASH,
        prioridade_clinica=PrioridadeClinica.MUITO_URGENTE,  # 2
    )

    with pytest.raises(
        ValidationError, match="Atendimento sem data de entrada na fila"
    ):
        atendimento.calcular_score_fila()

    atendimento.data_entrada_fila = entrada
    score = atendimento.calcular_score_fila()

    # Score = (prioridade * 10^12) + timestamp
    expected_score = (2 * 1_000_000_000_000) + epoch
    assert score == expected_score


def test_helpers_de_duracao_e_espera() -> None:
    t0 = datetime.now(UTC)
    t1 = t0 + timedelta(seconds=120)
    t2 = t1 + timedelta(seconds=600)

    atendimento = Atendimento(
        organizacao_id=1,
        paciente_id=uuid7(),
        data_entrada_fila=t0,
        chamada_iniciada_em=t1,
        chamada_finalizada_em=t2,
    )

    assert atendimento.tempo_espera_segundos == pytest.approx(120.0, 0.1)
    assert atendimento.duracao_chamada_segundos == pytest.approx(600.0, 0.1)
