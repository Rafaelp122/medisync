"""Testes unitários para modelos ricos e máquina de estados do módulo scheduling."""

from datetime import UTC, date, datetime, time, timedelta, timezone
from uuid import uuid4

import pytest
from src.core.errors import ValidationError
from src.modules.scheduling.domain.exceptions import TransicaoAgendamentoInvalidaError
from src.modules.scheduling.domain.models import (
    AgendaDisponibilidade,
    Agendamento,
    EspecialidadeAgenda,
    StatusAgendamento,
    normalizar_utc,
)


def test_normalizar_utc_converte_naive_e_com_offset() -> None:
    naive = datetime(2026, 11, 20, 10, 0)
    assert normalizar_utc(naive) == datetime(2026, 11, 20, 10, 0, tzinfo=UTC)

    brt = timezone(timedelta(hours=-3))
    aware = datetime(2026, 11, 20, 10, 0, tzinfo=brt)
    assert normalizar_utc(aware) == datetime(2026, 11, 20, 13, 0, tzinfo=UTC)


def test_agenda_disponibilidade_criacao_valida() -> None:
    prof_id = uuid4()
    disp = AgendaDisponibilidade(
        organizacao_id=1,
        profissional_id=prof_id,
        especialidade=EspecialidadeAgenda.PSICOLOGIA,
        dia_semana=0,
        hora_inicio=time(8, 0),
        hora_fim=time(12, 0),
        duracao_minutos=50,
    )
    assert disp.id is not None
    assert disp.organizacao_id == 1
    assert disp.profissional_id == prof_id
    assert disp.especialidade == EspecialidadeAgenda.PSICOLOGIA.value
    assert disp.dia_semana == 0
    assert disp.duracao_minutos == 50
    assert disp.ativo is True


@pytest.mark.parametrize(
    ("hora_inicio", "hora_fim", "duracao", "dia_semana"),
    [
        (time(12, 0), time(12, 0), 30, 0),
        (time(14, 0), time(12, 0), 30, 0),
        (time(8, 0), time(12, 0), 10, 0),
        (time(8, 0), time(12, 0), 150, 0),
        (time(8, 0), time(12, 0), 30, -1),
        (time(8, 0), time(12, 0), 30, 7),
        (time(8, 0, tzinfo=UTC), time(12, 0), 30, 0),
        (time(8, 0), time(12, 0, tzinfo=UTC), 30, 0),
    ],
)
def test_agenda_disponibilidade_rejeita_invariantes_invalidas(
    hora_inicio: time,
    hora_fim: time,
    duracao: int,
    dia_semana: int,
) -> None:
    with pytest.raises(ValidationError):
        AgendaDisponibilidade(
            organizacao_id=1,
            profissional_id=uuid4(),
            especialidade=EspecialidadeAgenda.NUTRICAO,
            dia_semana=dia_semana,
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
            duracao_minutos=duracao,
        )


def test_agenda_disponibilidade_rejeita_especialidade_invalida() -> None:
    with pytest.raises(ValidationError, match="CARDIOLOGIA"):
        AgendaDisponibilidade(
            organizacao_id=1,
            profissional_id=uuid4(),
            especialidade="CARDIOLOGIA",
            dia_semana=1,
            hora_inicio=time(8, 0),
            hora_fim=time(12, 0),
            duracao_minutos=30,
        )


def test_agenda_disponibilidade_sobrepoe() -> None:
    prof_id = uuid4()
    base = AgendaDisponibilidade(
        organizacao_id=1,
        profissional_id=prof_id,
        especialidade=EspecialidadeAgenda.PSICOLOGIA,
        dia_semana=0,
        hora_inicio=time(8, 0),
        hora_fim=time(12, 0),
        duracao_minutos=50,
    )
    sobreposta = AgendaDisponibilidade(
        organizacao_id=1,
        profissional_id=prof_id,
        especialidade=EspecialidadeAgenda.NUTRICAO,
        dia_semana=0,
        hora_inicio=time(11, 0),
        hora_fim=time(13, 0),
        duracao_minutos=30,
    )
    adjacente = AgendaDisponibilidade(
        organizacao_id=1,
        profissional_id=prof_id,
        especialidade=EspecialidadeAgenda.PSICOLOGIA,
        dia_semana=0,
        hora_inicio=time(12, 0),
        hora_fim=time(14, 0),
        duracao_minutos=50,
    )
    outro_dia = AgendaDisponibilidade(
        organizacao_id=1,
        profissional_id=prof_id,
        especialidade=EspecialidadeAgenda.PSICOLOGIA,
        dia_semana=1,
        hora_inicio=time(9, 0),
        hora_fim=time(11, 0),
        duracao_minutos=50,
    )
    inativa = AgendaDisponibilidade(
        organizacao_id=1,
        profissional_id=prof_id,
        especialidade=EspecialidadeAgenda.PSICOLOGIA,
        dia_semana=0,
        hora_inicio=time(9, 0),
        hora_fim=time(11, 0),
        duracao_minutos=50,
        ativo=False,
    )

    assert base.sobrepoe(sobreposta) is True
    assert sobreposta.sobrepoe(base) is True
    assert base.sobrepoe(adjacente) is False
    assert base.sobrepoe(outro_dia) is False
    assert base.sobrepoe(inativa) is False


def test_agenda_disponibilidade_gerar_intervalos_e_cobre_slot() -> None:
    # 2026-11-16 é segunda-feira (weekday == 0)
    segunda = date(2026, 11, 16)
    terca = date(2026, 11, 17)
    disp = AgendaDisponibilidade(
        organizacao_id=1,
        profissional_id=uuid4(),
        especialidade=EspecialidadeAgenda.PSICOLOGIA,
        dia_semana=0,
        hora_inicio=time(8, 0),
        hora_fim=time(10, 0),
        duracao_minutos=50,
    )

    intervalos = disp.gerar_intervalos(segunda)
    assert intervalos == [
        (
            datetime(2026, 11, 16, 8, 0, tzinfo=UTC),
            datetime(2026, 11, 16, 8, 50, tzinfo=UTC),
        ),
        (
            datetime(2026, 11, 16, 8, 50, tzinfo=UTC),
            datetime(2026, 11, 16, 9, 40, tzinfo=UTC),
        ),
    ]
    assert disp.gerar_intervalos(terca) == []

    # Cobre intervalos válidos da grade (inclusive com offset de fuso equivalente)
    brt = timezone(timedelta(hours=-3))
    assert (
        disp.cobre_slot(
            datetime(2026, 11, 16, 5, 0, tzinfo=brt),
            datetime(2026, 11, 16, 5, 50, tzinfo=brt),
        )
        is True
    )
    assert (
        disp.cobre_slot(
            datetime(2026, 11, 16, 8, 50, tzinfo=UTC),
            datetime(2026, 11, 16, 9, 40, tzinfo=UTC),
        )
        is True
    )
    # Rejeita desalinhado, duração divergente, estouro de janela e dia errado
    assert (
        disp.cobre_slot(
            datetime(2026, 11, 16, 8, 15, tzinfo=UTC),
            datetime(2026, 11, 16, 9, 5, tzinfo=UTC),
        )
        is False
    )
    assert (
        disp.cobre_slot(
            datetime(2026, 11, 16, 8, 0, tzinfo=UTC),
            datetime(2026, 11, 16, 8, 30, tzinfo=UTC),
        )
        is False
    )
    assert (
        disp.cobre_slot(
            datetime(2026, 11, 16, 9, 40, tzinfo=UTC),
            datetime(2026, 11, 16, 10, 30, tzinfo=UTC),
        )
        is False
    )
    assert (
        disp.cobre_slot(
            datetime(2026, 11, 17, 8, 0, tzinfo=UTC),
            datetime(2026, 11, 17, 8, 50, tzinfo=UTC),
        )
        is False
    )

    disp.ativo = False
    assert disp.gerar_intervalos(segunda) == []
    assert (
        disp.cobre_slot(
            datetime(2026, 11, 16, 8, 0, tzinfo=UTC),
            datetime(2026, 11, 16, 8, 50, tzinfo=UTC),
        )
        is False
    )


def _novo_agendamento(
    status: StatusAgendamento = StatusAgendamento.AGENDADO,
) -> Agendamento:
    inicio = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    return Agendamento(
        organizacao_id=1,
        paciente_id=uuid4(),
        profissional_id=uuid4(),
        especialidade=EspecialidadeAgenda.PSICOLOGIA,
        slot_inicio=inicio,
        slot_fim=inicio + timedelta(minutes=50),
        status=status,
        observacoes="Primeira sessão de acolhimento",
    )


def test_agendamento_iniciar_atendimento_e_cancelar_validos() -> None:
    ag = _novo_agendamento()
    assert ag.status == StatusAgendamento.AGENDADO.value

    atendimento_id = uuid4()
    ag.iniciar_atendimento(atendimento_id=atendimento_id)
    assert ag.status == StatusAgendamento.EM_ATENDIMENTO.value
    assert ag.atendimento_id == atendimento_id

    ag_confirmado = _novo_agendamento(status=StatusAgendamento.CONFIRMADO)
    ag_confirmado.cancelar()
    assert ag_confirmado.status == StatusAgendamento.CANCELADO.value

    ag_agendado = _novo_agendamento()
    ag_agendado.cancelar()
    assert ag_agendado.status == StatusAgendamento.CANCELADO.value


def test_agendamento_rejeita_transicoes_invalidas_e_nao_expoe_metodos_mortos() -> None:
    ag = _novo_agendamento()
    assert not hasattr(ag, "confirmar")
    assert not hasattr(ag, "concluir")
    assert not hasattr(ag, "marcar_falta")

    ag.cancelar()
    with pytest.raises(TransicaoAgendamentoInvalidaError, match="CANCELADO"):
        ag.iniciar_atendimento()

    ag_em_atendimento = _novo_agendamento(status=StatusAgendamento.EM_ATENDIMENTO)
    with pytest.raises(TransicaoAgendamentoInvalidaError, match="EM_ATENDIMENTO"):
        ag_em_atendimento.cancelar()


def test_agendamento_rejeita_slot_fim_menor_ou_igual_a_inicio() -> None:
    inicio = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        Agendamento(
            organizacao_id=1,
            paciente_id=uuid4(),
            profissional_id=uuid4(),
            especialidade=EspecialidadeAgenda.NUTRICAO,
            slot_inicio=inicio,
            slot_fim=inicio,
        )
