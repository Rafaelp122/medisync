"""Integration tests for queue ingestion, 64-bit scoring, and UUIDv7 FIFO."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from src.core.database import Base, async_session_factory, engine
from src.core.uuid7 import uuid7
from src.core.valkey import close_valkey_pool, get_valkey_client
from src.modules.queue.application.dtos import (
    AdquirirProximoPacienteCommand,
    AlocarChamadaCommand,
    IngressarFilaCommand,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.fila_service import (
    FilaService,
    calcular_score_fila,
)
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento

SAMPLE_TCLE_HASH = "a" * 64


@pytest.fixture(autouse=True)
async def clean_database_and_valkey() -> AsyncGenerator[None]:
    """Ensure clean PostgreSQL tables and Valkey keys for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "TRUNCATE TABLE atendimentos, dependentes, pacientes, "
                "profissionais, organizacoes CASCADE;"
            )
        )

    yield

    async for client in get_valkey_client():
        keys = await client.keys("fila:*")  # pyright: ignore[reportUnknownMemberType]
        keys.extend(await client.keys("lock:*"))  # pyright: ignore[reportUnknownMemberType]
        if keys:
            await client.delete(*keys)

    await close_valkey_pool()


@pytest.mark.asyncio
async def test_acceptance_criterion_1_urgency_precedence_rn01() -> None:
    """Patients with higher urgency (level 2) always precede lower urgency (level 4)."""
    now = datetime.now(UTC)
    org_id = 101

    # Patient A: Level 4 (Pouco Urgente), entered 2 hours ago
    id_a = uuid7()
    time_a = now - timedelta(hours=2)

    # Patient B: Level 2 (Muito Urgente), entered right now
    id_b = uuid7()
    time_b = now

    # Patient C: Level 3 (Urgente), entered 30 minutes ago
    id_c = uuid7()
    time_c = now - timedelta(minutes=30)

    # Patient D: Level 1 (Emergência), entered right now
    id_d = uuid7()
    time_d = now

    # Patient E: Level 5 (Não Urgente), entered 1 day ago
    id_e = uuid7()
    time_e = now - timedelta(days=1)

    async for valkey in get_valkey_client():
        async with async_session_factory() as session:
            service = FilaService(valkey=valkey, db_session=session)

            # Ingest in random/arbitrary order
            for item_id, prio, t in [
                (id_a, PrioridadeClinica.POUCO_URGENTE, time_a),
                (id_b, PrioridadeClinica.MUITO_URGENTE, time_b),
                (id_c, PrioridadeClinica.URGENTE, time_c),
                (id_d, PrioridadeClinica.EMERGENCIA, time_d),
                (id_e, PrioridadeClinica.NAO_URGENTE, time_e),
            ]:
                await service.ingressar_fila(
                    IngressarFilaCommand(
                        organizacao_id=org_id,
                        atendimento_id=item_id,
                        prioridade_clinica=prio,
                        data_entrada_fila=t,
                    )
                )

            # Retrieve complete queue ordered by Valkey ZSET ascending score
            ordered_queue = await service.listar_fila(org_id, limit=10)

            # Must be strictly ordered: Level 1 (D) -> 2 (B) -> 3 (C) -> 4 (A) -> 5 (E)
            expected_order = [str(id_d), str(id_b), str(id_c), str(id_a), str(id_e)]
            assert ordered_queue == expected_order

            # Verify positions
            assert await service.obter_posicao_fila(org_id, id_d) == 1
            assert await service.obter_posicao_fila(org_id, id_b) == 2
            assert await service.obter_posicao_fila(org_id, id_c) == 3
            assert await service.obter_posicao_fila(org_id, id_a) == 4
            assert await service.obter_posicao_fila(org_id, id_e) == 5
            assert await service.obter_tamanho_fila(org_id) == 5


@pytest.mark.asyncio
async def test_acceptance_criterion_2_uuidv7_sub_millisecond_fifo() -> None:
    """Within same priority, exact FIFO is maintained via UUIDv7 tie-breaking."""
    org_id = 102
    fixed_time = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)
    priority = PrioridadeClinica.URGENTE

    # Generate 2 UUIDv7 IDs sequentially with small sleep to ensure distinct millisecond
    id_1 = uuid7()
    await asyncio.sleep(0.01)  # 10ms later
    id_2 = uuid7()

    # Verify that id_1 is strictly lexicographically smaller than id_2
    assert str(id_1) < str(id_2)

    async for valkey in get_valkey_client():
        async with async_session_factory() as session:
            service = FilaService(valkey=valkey, db_session=session)

            # Ingest in REVERSE order: id_2 FIRST, id_1 SECOND
            await service.ingressar_fila(
                IngressarFilaCommand(
                    organizacao_id=org_id,
                    atendimento_id=id_2,
                    prioridade_clinica=priority,
                    data_entrada_fila=fixed_time,
                )
            )
            await service.ingressar_fila(
                IngressarFilaCommand(
                    organizacao_id=org_id,
                    atendimento_id=id_1,
                    prioridade_clinica=priority,
                    data_entrada_fila=fixed_time,
                )
            )

            # Verify both have the EXACT same numerical score
            k_fila = f"fila:{org_id}:aptos"
            score_1 = await valkey.zscore(k_fila, str(id_1))  # pyright: ignore[reportUnknownMemberType]
            score_2 = await valkey.zscore(k_fila, str(id_2))  # pyright: ignore[reportUnknownMemberType]
            assert score_1 == score_2
            assert score_1 == float(calcular_score_fila(priority, fixed_time))

            # Valkey ZSET must sort id_1 BEFORE id_2 due to lexicographical tie-breaking
            queue = await service.listar_fila(org_id)
            assert queue == [str(id_1), str(id_2)]
            assert await service.obter_posicao_fila(org_id, id_1) == 1
            assert await service.obter_posicao_fila(org_id, id_2) == 2


@pytest.mark.asyncio
async def test_acceptance_criterion_3_retry_loop_allocates_second_patient() -> None:
    """Retry loop seamlessly allocates 2nd patient when 1st patient was snatched."""
    org_id = 103

    async with async_session_factory() as session:
        # 1. Setup DB records (1 org, 2 patients, 2 doctors, 2 attendances)
        org = make_organizacao(
            cnpj="11223344000199", razao_social="UBS Concurrency Retry"
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)
        org_id = org.id

        paciente_1 = make_paciente(org_id, cpf="11122233344")
        paciente_2 = make_paciente(org_id, cpf="55566677788")
        medico_1 = make_profissional(
            org_id,
            cpf="99988877766",
            email="dr.winner@ubs.gov.br",
            papel="MEDICO",
        )
        medico_2 = make_profissional(
            org_id,
            cpf="44433322211",
            email="dra.runnerup@ubs.gov.br",
            papel="MEDICO",
        )
        session.add_all([paciente_1, paciente_2, medico_1, medico_2])
        await session.commit()
        await session.refresh(paciente_1)
        await session.refresh(paciente_2)
        await session.refresh(medico_1)
        await session.refresh(medico_2)

        # Create two attendances promoted to APTO_PARA_CHAMADA
        now = datetime.now(UTC)
        atend_1 = make_atendimento(
            organizacao_id=org_id,
            paciente_id=paciente_1.id,
            prioridade_clinica=PrioridadeClinica.URGENTE,
            tcle_hash=SAMPLE_TCLE_HASH,
        )
        atend_1.promover_para_apto()
        atend_1.data_entrada_fila = now - timedelta(minutes=10)

        atend_2 = make_atendimento(
            organizacao_id=org_id,
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
        async with async_session_factory() as session:
            alocacao_service = AlocacaoChamadaService(
                valkey=valkey,
                db_session=session,
                lua_manager=get_lua_script_manager(),
            )
            fila_service = FilaService(
                valkey=valkey,
                db_session=session,
                alocacao_service=alocacao_service,
            )

            # Ingest both attendances into Valkey queue
            await fila_service.ingressar_fila(
                IngressarFilaCommand(
                    organizacao_id=org_id,
                    atendimento_id=atend_1.id,
                    prioridade_clinica=atend_1.prioridade_clinica,
                    data_entrada_fila=atend_1.data_entrada_fila,
                )
            )
            await fila_service.ingressar_fila(
                IngressarFilaCommand(
                    organizacao_id=org_id,
                    atendimento_id=atend_2.id,
                    prioridade_clinica=atend_2.prioridade_clinica,
                    data_entrada_fila=atend_2.data_entrada_fila,
                )
            )

            # Initial queue state: atend_1 is #1, atend_2 is #2
            assert await fila_service.listar_fila(org_id) == [
                str(atend_1.id),
                str(atend_2.id),
            ]

            # Doctor 1 directly snatches Patient 1 (atend_1) via alocar_chamada
            res_medico_1 = await alocacao_service.alocar_chamada(
                AlocarChamadaCommand(
                    organizacao_id=org_id,
                    medico_id=medico_1.id,
                    atendimento_id=atend_1.id,
                )
            )
            assert res_medico_1.atendimento_id == atend_1.id
            assert res_medico_1.medico_id == medico_1.id

            # Doctor 2 concurrently calls adquirir_proximo_paciente.
            # Doctor 2 will see atend_2 as top and acquire atend_2 smoothly.
            res_medico_2 = await fila_service.adquirir_proximo_paciente(
                AdquirirProximoPacienteCommand(
                    organizacao_id=org_id,
                    medico_id=medico_2.id,
                    max_retries=3,
                )
            )
            assert res_medico_2 is not None
            assert res_medico_2.atendimento_id == atend_2.id
            assert res_medico_2.medico_id == medico_2.id

            # Verify queue is now completely empty
            assert await fila_service.obter_tamanho_fila(org_id) == 0

            # Verify PostgreSQL state for both attendances
            db_atend_1 = await session.get(Atendimento, atend_1.id)
            db_atend_2 = await session.get(Atendimento, atend_2.id)

            assert db_atend_1 is not None
            assert db_atend_1.status == StatusAtendimento.CHAMANDO_PACIENTE.value
            assert db_atend_1.medico_id == medico_1.id

            assert db_atend_2 is not None
            assert db_atend_2.status == StatusAtendimento.CHAMANDO_PACIENTE.value
            assert db_atend_2.medico_id == medico_2.id
