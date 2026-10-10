"""Integration tests for atomic allocation, 50-doctor race, and latency benchmark."""

import asyncio
import time
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from src.core.database import async_session_factory
from src.core.uuid7 import uuid7
from src.core.valkey import get_valkey_client
from src.modules.queue.application.dtos import AlocarChamadaCommand
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.domain.exceptions import MedicoOcupadoError
from src.modules.queue.domain.models import Atendimento, StatusAtendimento
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager

from tests.factories.scenarios import seed_clinical_scenario

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_parallel_race_condition_50_doctors_single_winner() -> None:
    """Stress test: 50 concurrent doctors competing for 1 patient.

    Expect exactly 1 winner (code 1) and 49 losers (code -1).
    """
    manager = get_lua_script_manager()
    org_id = 999
    atendimento_id = str(uuid7())
    k_fila = f"fila:{org_id}:aptos"
    k_atend_lock = f"lock:{org_id}:atendimento:{atendimento_id}"

    async for client in get_valkey_client():
        # Clean and seed queue with single patient
        await client.delete(k_fila, k_atend_lock)
        await client.zadd(k_fila, {atendimento_id: 2000})  # pyright: ignore[reportUnknownMemberType]

        # Preload script
        await manager.preload_scripts(client)

        async def attempt_call(doc_idx: int, cl: Redis = client) -> int:
            doc_id = f"doc-concurrency-{doc_idx}"
            k_doc = f"lock:{org_id}:medico:{doc_id}"
            await cl.delete(k_doc)
            res = await manager.execute_script(
                client=cl,
                script_name="alocar_chamada",
                keys=[k_doc, k_atend_lock, k_fila],
                args=[doc_id, atendimento_id, 45],
            )
            return int(res)

        # Launch 50 simultaneous doctors
        tasks = [attempt_call(i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        winners = [r for r in results if r == 1]
        losers = [r for r in results if r == -1]

        # Exact invariants: zero overbooking
        assert len(winners) == 1, f"Expected 1 winner, got {len(winners)}"
        assert len(losers) == 49, f"Expected 49 losers, got {len(losers)}"

        # Queue must be empty
        assert (
            await client.zcard(k_fila)  # pyright: ignore[reportUnknownMemberType]
            == 0
        )

        # Attendance lock must exist and point to the winning doctor
        atend_lock_val = await client.get(k_atend_lock)
        assert atend_lock_val is not None
        assert str(atend_lock_val).startswith("doc-concurrency-")

        # Winner doctor lock must exist and point to attendance
        winner_doc_id = str(atend_lock_val)
        winner_doc_lock = await client.get(f"lock:{org_id}:medico:{winner_doc_id}")
        assert winner_doc_lock == atendimento_id

        # TTL must be within expected ring range
        ttl = await client.ttl(k_atend_lock)
        assert 40 <= ttl <= 45


@pytest.mark.asyncio
async def test_doctor_active_lock_returns_0_conflict() -> None:
    """Verify doctor with active call lock receives 0 from Lua and 409 from service."""
    org_id = 999
    medico_id = uuid4()
    atendimento_id = uuid7()
    k_medico = f"lock:{org_id}:medico:{medico_id}"
    k_atend = f"lock:{org_id}:atendimento:{atendimento_id}"
    k_fila = f"fila:{org_id}:aptos"

    async for client in get_valkey_client():
        # Setup: doctor is already busy with another call
        await client.set(k_medico, "active-call-id", ex=45)
        await client.zadd(k_fila, {str(atendimento_id): 1000})  # pyright: ignore[reportUnknownMemberType]

        manager = get_lua_script_manager()
        res = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico, k_atend, k_fila],
            args=[str(medico_id), str(atendimento_id), 45],
        )
        assert res == 0, "Expected code 0 when doctor has active lock"

        # Also verify application service translates code 0 to MedicoOcupadoError
        async with async_session_factory() as session:
            service = AlocacaoChamadaService(
                valkey=client,
                db_session=session,
                lua_manager=manager,
            )
            cmd = AlocarChamadaCommand(
                organizacao_id=org_id,
                medico_id=medico_id,
                atendimento_id=atendimento_id,
            )
            with pytest.raises(MedicoOcupadoError, match="já possui uma chamada"):
                await service.alocar_chamada(cmd)


@pytest.mark.asyncio
async def test_alocar_chamada_sub_10ms_latency_benchmark() -> None:
    """Benchmark: assert script execution time on Valkey is < 10 ms (RNF-01)."""
    manager = get_lua_script_manager()
    org_id = 888
    k_fila = f"fila:{org_id}:aptos"

    async for client in get_valkey_client():
        await manager.preload_scripts(client)

        latencies_ms: list[float] = []

        # Run 50 sequential allocations to evaluate steady-state latency
        for i in range(50):
            atend_id = f"bench-atend-{i}"
            med_id = f"bench-med-{i}"
            k_med = f"lock:{org_id}:medico:{med_id}"
            k_atend = f"lock:{org_id}:atendimento:{atend_id}"

            await client.zadd(k_fila, {atend_id: 1000 + i})  # pyright: ignore[reportUnknownMemberType]

            start = time.perf_counter()
            res = await manager.execute_script(
                client=client,
                script_name="alocar_chamada",
                keys=[k_med, k_atend, k_fila],
                args=[med_id, atend_id, 45],
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies_ms.append(elapsed_ms)

            assert res == 1

        avg_latency = sum(latencies_ms) / len(latencies_ms)
        sorted_latencies = sorted(latencies_ms)
        p99_latency = sorted_latencies[int(len(sorted_latencies) * 0.98)]

        # RNF-01 requirement: allocation < 10ms (and well under 200ms ceiling)
        assert avg_latency < 10.0, (
            f"Expected average latency < 10ms, got {avg_latency:.2f}ms"
        )
        assert p99_latency < 20.0, (
            f"Expected p99 latency < 20ms, got {p99_latency:.2f}ms"
        )


@pytest.mark.asyncio
async def test_end_to_end_alocacao_service_with_postgres() -> None:
    """Verify end-to-end atomic allocation with PostgreSQL and Valkey consistency."""
    async with async_session_factory() as session:
        # 1. Setup DB records via seed_clinical_scenario
        SAMPLE_TCLE_HASH = (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        cenario = await seed_clinical_scenario(
            session,
            org_cnpj="88776655000144",
            org_razao_social="UBS Concurrency",
            paciente_cpf="33344455566",
            medico_cpf="77788899900",
            medico_email="dra.alocacao@ubs.gov.br",
            status_atendimento=StatusAtendimento.APTO_PARA_CHAMADA,
            tcle_hash=SAMPLE_TCLE_HASH,
        )
        org = cenario.organizacao
        medico = cenario.medico
        atendimento = cenario.atendimento
        atendimento.medico_id = None
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        atend_id = atendimento.id
        med_id = medico.id

        # 2. Add to Valkey queue
        async for client in get_valkey_client():
            k_fila = f"fila:{org.id}:aptos"
            await client.zadd(k_fila, {str(atend_id): 1000})  # pyright: ignore[reportUnknownMemberType]

            # 3. Execute allocation via service
            service = AlocacaoChamadaService(
                valkey=client,
                db_session=session,
                lua_manager=get_lua_script_manager(),
            )
            cmd = AlocarChamadaCommand(
                organizacao_id=org.id,
                medico_id=med_id,
                atendimento_id=atend_id,
                ttl_segundos=45,
            )
            result = await service.alocar_chamada(cmd)

            # Assert returned DTO
            assert result.atendimento_id == atend_id
            assert result.medico_id == med_id
            assert result.status == StatusAtendimento.CHAMANDO_PACIENTE.value
            assert result.ttl_segundos == 45

            # 4. Verify DB entity state
            reloaded = await session.get(Atendimento, atend_id)
            assert reloaded is not None
            assert reloaded.status == StatusAtendimento.CHAMANDO_PACIENTE.value
            assert reloaded.medico_id == med_id
            assert reloaded.chamada_iniciada_em is not None

            # 5. Verify Valkey dual locks and queue removal
            k_med = f"lock:{org.id}:medico:{med_id}"
            k_atend = f"lock:{org.id}:atendimento:{atend_id}"
            assert await client.get(k_med) == str(atend_id)
            assert await client.get(k_atend) == str(med_id)
            assert (
                await client.zrank(k_fila, str(atend_id))  # pyright: ignore[reportUnknownMemberType]
                is None
            )

            # 6. Verify lock checking helpers on service
            assert await service.verificar_lock_medico(org.id, med_id) is True
            assert await service.verificar_lock_atendimento(org.id, atend_id) is True
            assert await service.obter_lock_medico_atendimento_id(
                org.id, med_id
            ) == str(atend_id)

            # 7. Release locks
            await service.liberar_locks(org.id, med_id, atend_id)
            assert await service.verificar_lock_medico(org.id, med_id) is False
            assert await service.verificar_lock_atendimento(org.id, atend_id) is False
