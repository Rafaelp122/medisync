"""Integration tests for queue ingestion, 64-bit scoring, and UUIDv7 FIFO."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from src.core.database import get_session_factory
from src.core.uuid7 import uuid7
from src.core.valkey import get_valkey_client
from src.modules.queue.application.dtos import (
    AdquirirProximoPacienteCommand,
    AlocarChamadaCommand,
    IngressarFilaCommand,
)
from src.modules.queue.composition import (
    build_alocacao_service_for_session,
    build_fila_service_for_session,
)
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)
from src.modules.queue.domain.scoring import calcular_score
from src.modules.queue.infrastructure.valkey_queue_engine import FILA_APTOS_KEY

from tests.factories.identity import make_paciente, make_profissional
from tests.factories.queue import make_atendimento

SAMPLE_TCLE_HASH = "a" * 64


pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_acceptance_criterion_1_urgency_precedence_rn01() -> None:
    """Patients with higher urgency (level 2) always precede lower urgency (level 4)."""
    now = datetime.now(UTC)

    id_a = uuid7()
    time_a = now - timedelta(hours=2)
    id_b = uuid7()
    time_b = now
    id_c = uuid7()
    time_c = now - timedelta(minutes=30)
    id_d = uuid7()
    time_d = now
    id_e = uuid7()
    time_e = now - timedelta(days=1)

    async for valkey in get_valkey_client():
        async with get_session_factory()() as session:
            service = build_fila_service_for_session(session=session, valkey=valkey)

            for item_id, prio, t in [
                (id_a, PrioridadeClinica.POUCO_URGENTE, time_a),
                (id_b, PrioridadeClinica.MUITO_URGENTE, time_b),
                (id_c, PrioridadeClinica.URGENTE, time_c),
                (id_d, PrioridadeClinica.EMERGENCIA, time_d),
                (id_e, PrioridadeClinica.NAO_URGENTE, time_e),
            ]:
                await service.ingressar_fila(
                    IngressarFilaCommand(
                        atendimento_id=item_id,
                        prioridade_clinica=prio,
                        data_entrada_fila=t,
                    )
                )

            ordered_queue: list[str] = await valkey.zrange(FILA_APTOS_KEY, 0, 9)  # pyright: ignore[reportUnknownMemberType]
            expected_order = [str(id_d), str(id_b), str(id_c), str(id_a), str(id_e)]
            assert ordered_queue == expected_order

            assert await service.obter_posicao_fila(id_d) == 1
            assert await service.obter_posicao_fila(id_b) == 2
            assert await service.obter_posicao_fila(id_c) == 3
            assert await service.obter_posicao_fila(id_a) == 4
            assert await service.obter_posicao_fila(id_e) == 5
            assert await service.obter_tamanho_fila() == 5


@pytest.mark.asyncio
async def test_acceptance_criterion_2_uuidv7_sub_millisecond_fifo() -> None:
    """Within same priority, exact FIFO is maintained via UUIDv7 tie-breaking."""
    fixed_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)
    priority = PrioridadeClinica.URGENTE

    id_1 = uuid7()
    await asyncio.sleep(0.01)
    id_2 = uuid7()

    assert str(id_1) < str(id_2)

    async for valkey in get_valkey_client():
        async with get_session_factory()() as session:
            service = build_fila_service_for_session(session=session, valkey=valkey)

            await service.ingressar_fila(
                IngressarFilaCommand(
                    atendimento_id=id_2,
                    prioridade_clinica=priority,
                    data_entrada_fila=fixed_time,
                )
            )
            await service.ingressar_fila(
                IngressarFilaCommand(
                    atendimento_id=id_1,
                    prioridade_clinica=priority,
                    data_entrada_fila=fixed_time,
                )
            )

            score_1 = await valkey.zscore(FILA_APTOS_KEY, str(id_1))  # pyright: ignore[reportUnknownMemberType]
            score_2 = await valkey.zscore(FILA_APTOS_KEY, str(id_2))  # pyright: ignore[reportUnknownMemberType]
            assert score_1 == score_2
            assert score_1 == float(calcular_score(priority, fixed_time))

            queue: list[str] = await valkey.zrange(FILA_APTOS_KEY, 0, -1)  # pyright: ignore[reportUnknownMemberType]
            assert queue == [str(id_1), str(id_2)]
            assert await service.obter_posicao_fila(id_1) == 1
            assert await service.obter_posicao_fila(id_2) == 2


@pytest.mark.asyncio
async def test_acceptance_criterion_3_atomic_scan_allocates_second_patient() -> None:
    """Atomic Lua scan allocates 2nd patient when 1st patient was snatched."""
    async with get_session_factory()() as session:
        paciente_1 = make_paciente(cpf="11122233344", telefone="11987654301")
        paciente_2 = make_paciente(cpf="55566677788", telefone="11987654302")
        medico_1 = make_profissional(
            cpf="99988877766",
            email="dr.winner@ubs.gov.br",
            papel="MEDICO",
            crm="11111",
            crm_uf="SP",
        )
        medico_2 = make_profissional(
            cpf="44433322211",
            email="dra.runnerup@ubs.gov.br",
            papel="MEDICO",
            crm="22222",
            crm_uf="SP",
        )
        session.add_all([paciente_1, paciente_2, medico_1, medico_2])
        await session.commit()
        await session.refresh(paciente_1)
        await session.refresh(paciente_2)
        await session.refresh(medico_1)
        await session.refresh(medico_2)

        now = datetime.now(UTC)
        atend_1 = make_atendimento(
            paciente_id=paciente_1.id,
            prioridade_clinica=PrioridadeClinica.URGENTE,
            tcle_hash=SAMPLE_TCLE_HASH,
        )
        atend_1.promover_para_apto()
        atend_1.data_entrada_fila = now - timedelta(minutes=10)

        atend_2 = make_atendimento(
            paciente_id=paciente_2.id,
            prioridade_clinica=PrioridadeClinica.URGENTE,
            tcle_hash=SAMPLE_TCLE_HASH,
        )
        atend_2.promover_para_apto()
        atend_2.data_entrada_fila = now - timedelta(minutes=5)

        session.add_all([atend_1, atend_2])
        await session.commit()
        await session.refresh(atend_1)
        await session.refresh(atend_2)

    async for valkey in get_valkey_client():
        async with get_session_factory()() as session:
            alocacao_service = build_alocacao_service_for_session(
                valkey=valkey,
                session=session,
            )
            fila_service = build_fila_service_for_session(
                session=session,
                valkey=valkey,
            )

            await fila_service.ingressar_fila(
                IngressarFilaCommand(
                    atendimento_id=atend_1.id,
                    prioridade_clinica=atend_1.prioridade_clinica,
                    data_entrada_fila=atend_1.data_entrada_fila,
                )
            )
            await fila_service.ingressar_fila(
                IngressarFilaCommand(
                    atendimento_id=atend_2.id,
                    prioridade_clinica=atend_2.prioridade_clinica,
                    data_entrada_fila=atend_2.data_entrada_fila,
                )
            )

            queued_ids: list[str] = await valkey.zrange(FILA_APTOS_KEY, 0, -1)  # pyright: ignore[reportUnknownMemberType]
            assert queued_ids == [str(atend_1.id), str(atend_2.id)]

            res_medico_1 = await alocacao_service.alocar_chamada(
                AlocarChamadaCommand(
                    medico_id=medico_1.id,
                    atendimento_id=atend_1.id,
                )
            )
            assert res_medico_1.atendimento_id == atend_1.id
            assert res_medico_1.medico_id == medico_1.id

            res_medico_2 = await fila_service.adquirir_proximo_paciente(
                AdquirirProximoPacienteCommand(
                    medico_id=medico_2.id,
                    max_scan=50,
                )
            )
            assert res_medico_2 is not None
            assert res_medico_2.atendimento_id == atend_2.id
            assert res_medico_2.medico_id == medico_2.id

            assert await fila_service.obter_tamanho_fila() == 0

            db_atend_1 = await session.get(Atendimento, atend_1.id)
            db_atend_2 = await session.get(Atendimento, atend_2.id)

            assert db_atend_1 is not None
            assert db_atend_1.status == StatusAtendimento.CHAMANDO_PACIENTE.value
            assert db_atend_1.medico_id == medico_1.id

            assert db_atend_2 is not None
            assert db_atend_2.status == StatusAtendimento.CHAMANDO_PACIENTE.value
            assert db_atend_2.medico_id == medico_2.id
