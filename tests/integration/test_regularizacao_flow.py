"""Integration tests for attendance regularization and contingency flow.

Rules: US-05, RF-05, RN01, RN03.
"""

from datetime import UTC, datetime, timedelta

import pytest
from src.core.context import tenant_context
from src.core.database import async_session_factory
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

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)

SAMPLE_TCLE_HASH = "a" * 64

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_e2e_regularizacao_contingencia_restaura_antiguidade() -> None:
    """Paciente regularizado restaura primazia por antiguidade (RN01, RN03, US-05)."""
    now = datetime.now(UTC)
    org_id = 201

    async with async_session_factory() as session:
        org = make_organizacao(
            id=org_id,
            cnpj="99887766000155",
            razao_social="Hospital Regularizacao E2E",
        )
        paciente_1 = make_paciente(org_id, cpf="11122233344")
        paciente_2 = make_paciente(org_id, cpf="55566677788")
        medico_1 = make_profissional(
            org_id,
            cpf="99988877766",
            email="dr.regularizacao@medisync.local",
            papel="MEDICO",
        )
        session.add_all([org, paciente_1, paciente_2, medico_1])
        await session.commit()
        await session.refresh(paciente_1)
        await session.refresh(paciente_2)
        await session.refresh(medico_1)

        # Paciente 1 chegou há 25 minutos (T0) e ficou retido na elegibilidade
        t0 = now - timedelta(minutes=25)
        atend_1 = Atendimento(
            organizacao_id=org_id,
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
            organizacao_id=org_id,
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
            res_2 = await service.admitir_atendimento_apto(org_id, atend_2.id)
            assert res_2.promovido is True

            # Paciente 1 agora aciona regularização por contingência assistencial
            cmd_regularizar = RegularizacaoFilaCommand(
                organizacao_id=org_id,
                atendimento_id=atend_1.id,
                motivo="Indisponibilidade temporária de autorização da operadora",
                tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
            )
            res_1 = await service.regularizar_atendimento(cmd_regularizar)
            assert res_1.promovido is True
            assert res_1.status == StatusAtendimento.APTO_PARA_CHAMADA.value

            # Validação no Valkey ZSET: Paciente 1 DEVE ter menor score
            k_fila = f"fila:{org_id}:aptos"
            score_1 = await valkey.zscore(k_fila, str(atend_1.id))
            score_2 = await valkey.zscore(k_fila, str(atend_2.id))
            assert score_1 is not None and score_2 is not None
            assert score_1 < score_2, "Score de P1 deve ser menor (T0 < T1)"

            rank_1 = await valkey.zrank(k_fila, str(atend_1.id))
            rank_2 = await valkey.zrank(k_fila, str(atend_2.id))
            assert rank_1 == 0, "Paciente 1 deve ser o topo da fila (rank 0)"
            assert rank_2 == 1, "Paciente 2 deve ser o segundo da fila (rank 1)"

            # Convocação médica aloca obrigatoriamente Paciente 1
            with tenant_context(org_id):
                alocacao = await service.adquirir_proximo_paciente(
                    AdquirirProximoPacienteCommand(
                        organizacao_id=org_id,
                        medico_id=medico_1.id,
                    )
                )
            assert alocacao is not None
            assert alocacao.atendimento_id == atend_1.id


@pytest.mark.asyncio
async def test_e2e_corrida_concorrente_retorno_worker_e_contingencia() -> None:
    """Disparo quase simultâneo é tratado com idempotência estrita."""
    org_id = 202

    async with async_session_factory() as session:
        org = make_organizacao(
            id=org_id,
            cnpj="11223344000188",
            razao_social="Hospital Concorrencia E2E",
        )
        paciente = make_paciente(org_id, cpf="33344455566")
        session.add_all([org, paciente])
        await session.commit()
        await session.refresh(paciente)

        atend = Atendimento(
            organizacao_id=org_id,
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
                organizacao_id=org_id,
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
            k_fila = f"fila:{org_id}:aptos"
            total = await valkey.zcard(k_fila)
            assert total == 1
