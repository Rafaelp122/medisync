"""Integration tests for attendance regularization and contingency flow.

Rules: US-05, RF-05, RN01, RN03.
"""

from datetime import UTC, datetime, timedelta

import pytest
from src.core.database import get_session_factory
from src.core.uuid7 import uuid7
from src.core.valkey import get_valkey_client
from src.modules.queue.application.dtos import (
    AdquirirProximoPacienteCommand,
    RegularizacaoFilaCommand,
)
from src.modules.queue.composition import build_fila_service_for_session
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)

from tests.factories.identity import make_paciente, make_profissional

SAMPLE_TCLE_HASH = "a" * 64

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_e2e_regularizacao_contingencia_restaura_antiguidade() -> None:
    """Paciente regularizado restaura primazia por antiguidade (RN01, RN03, US-05)."""
    now = datetime.now(UTC)

    async with get_session_factory()() as session:
        paciente_1 = make_paciente(cpf="11122233344", telefone="11987654301")
        paciente_2 = make_paciente(cpf="55566677788", telefone="11987654302")
        medico_1 = make_profissional(
            cpf="99988877766",
            email="dr.regularizacao@medisync.local",
            papel="MEDICO",
        )
        session.add_all([paciente_1, paciente_2, medico_1])
        await session.commit()
        await session.refresh(paciente_1)
        await session.refresh(paciente_2)
        await session.refresh(medico_1)

        # Paciente 1 chegou há 25 minutos (T0) e ficou retido na elegibilidade
        t0 = now - timedelta(minutes=25)
        atend_1 = Atendimento(
            paciente_id=paciente_1.id,
            prioridade_clinica=PrioridadeClinica.URGENTE,
            tcle_hash=SAMPLE_TCLE_HASH,
            status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
            data_entrada_fila=t0,
            criado_em=t0,
            id=uuid7(),
        )

        # Paciente 2 chegou há 5 minutos (T1), aprovado de imediato na fila
        t1 = now - timedelta(minutes=5)
        atend_2 = Atendimento(
            paciente_id=paciente_2.id,
            prioridade_clinica=PrioridadeClinica.URGENTE,
            tcle_hash=SAMPLE_TCLE_HASH,
            status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
            data_entrada_fila=t1,
            criado_em=t1,
            id=uuid7(),
        )
        session.add_all([atend_1, atend_2])
        await session.commit()

        async for valkey in get_valkey_client():
            service = build_fila_service_for_session(session=session, valkey=valkey)

            # Promove Paciente 2 (imediato)
            res_2 = await service.admitir_atendimento_apto(atend_2.id)
            assert res_2.promovido is True

            # Paciente 1 agora aciona regularização por contingência assistencial
            cmd_regularizar = RegularizacaoFilaCommand(
                atendimento_id=atend_1.id,
                motivo="Indisponibilidade temporária de autorização da operadora",
                tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
            )
            res_1 = await service.regularizar_atendimento(cmd_regularizar)
            assert res_1.promovido is True
            assert res_1.status == StatusAtendimento.APTO_PARA_CHAMADA.value

            # Validação no Valkey ZSET: Paciente 1 DEVE ter menor score
            k_fila = "fila:aptos"
            score_1 = await valkey.zscore(k_fila, str(atend_1.id))
            score_2 = await valkey.zscore(k_fila, str(atend_2.id))
            assert score_1 is not None and score_2 is not None
            assert score_1 < score_2, "Score de P1 deve ser menor (T0 < T1)"

            rank_1 = await valkey.zrank(k_fila, str(atend_1.id))
            rank_2 = await valkey.zrank(k_fila, str(atend_2.id))
            assert rank_1 == 0, "Paciente 1 deve ser o topo da fila (rank 0)"
            assert rank_2 == 1, "Paciente 2 deve ser o segundo da fila (rank 1)"

            # Convocação médica aloca obrigatoriamente Paciente 1
            alocacao = await service.adquirir_proximo_paciente(
                AdquirirProximoPacienteCommand(medico_id=medico_1.id)
            )
            assert alocacao is not None
            assert alocacao.atendimento_id == atend_1.id


@pytest.mark.asyncio
async def test_e2e_corrida_concorrente_retorno_worker_e_contingencia() -> None:
    """Disparo quase simultâneo é tratado com idempotência estrita."""
    async with get_session_factory()() as session:
        paciente = make_paciente(cpf="33344455566")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atend = Atendimento(
            paciente_id=paciente.id,
            prioridade_clinica=PrioridadeClinica.MUITO_URGENTE,
            tcle_hash=SAMPLE_TCLE_HASH,
            status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
            id=uuid7(),
        )
        session.add(atend)
        await session.commit()

        async for valkey in get_valkey_client():
            service = build_fila_service_for_session(session=session, valkey=valkey)

            # Primeira chamada: regularização
            cmd = RegularizacaoFilaCommand(
                atendimento_id=atend.id,
                motivo="Aprovação simultânea da operadora",
                tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
            )
            res_first = await service.regularizar_atendimento(cmd)
            assert res_first.promovido is True

            # Segunda chamada (idempotente - ex: worker ARQ ou duplo clique)
            res_second = await service.regularizar_atendimento(cmd)
            assert res_second.promovido is False
            assert res_second.status == "already_promoted"

            # ZSET deve conter apenas 1 entrada para o atendimento
            total = await valkey.zcard("fila:aptos")
            assert total == 1
