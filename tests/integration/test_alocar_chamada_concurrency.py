"""Integration tests for atomic allocation, 4-Keys protection, and concurrency."""

import asyncio
import time
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from src.core.database import get_session_factory
from src.core.uuid7 import uuid7
from src.core.valkey import get_valkey_client
from src.modules.queue.application.dtos import (
    AdquirirProximoPacienteCommand,
    AlocarChamadaCommand,
)
from src.modules.queue.composition import (
    build_alocacao_service_for_session,
    build_fila_service_for_session,
    build_queue_engine,
)
from src.modules.queue.domain.exceptions import MedicoOcupadoError
from src.modules.queue.domain.models import Atendimento, StatusAtendimento
from src.modules.queue.domain.scoring import calcular_score
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager

from tests.factories.identity import make_paciente, make_profissional
from tests.factories.queue import make_atendimento
from tests.factories.scenarios import seed_clinical_scenario

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_parallel_race_condition_50_doctors_single_winner() -> None:
    """Stress test: 50 concurrent doctors competing for 1 patient.

    Expect exactly 1 winner (code 1) and 49 losers (code -1).
    """
    manager = get_lua_script_manager()
    atendimento_id = str(uuid7())
    k_fila = "fila:aptos"
    k_atend_lock = f"lock:atendimento:{atendimento_id}"

    async for client in get_valkey_client():
        await client.delete(k_fila, k_atend_lock)
        await client.zadd(k_fila, {atendimento_id: 2000})  # pyright: ignore[reportUnknownMemberType]
        await manager.preload_scripts(client)

        async def attempt_call(doc_idx: int, cl: Redis = client) -> int:
            doc_id = f"doc-concurrency-{doc_idx}"
            k_doc = f"lock:medico:{doc_id}"
            k_consulta = f"lock:consulta_ativa:medico:{doc_id}"
            await cl.delete(k_doc, k_consulta)
            res = await manager.execute_script(
                client=cl,
                script_name="alocar_chamada",
                keys=[k_doc, k_atend_lock, k_fila, k_consulta],
                args=[doc_id, atendimento_id, 45],
            )
            return int(res)

        tasks = [attempt_call(i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        winners = [r for r in results if r == 1]
        losers = [r for r in results if r == -1]

        assert len(winners) == 1, f"Expected 1 winner, got {len(winners)}"
        assert len(losers) == 49, f"Expected 49 losers, got {len(losers)}"
        assert await client.zcard(k_fila) == 0  # pyright: ignore[reportUnknownMemberType]

        atend_lock_val = await client.get(k_atend_lock)
        assert atend_lock_val is not None
        assert str(atend_lock_val).startswith("doc-concurrency-")

        winner_doc_id = str(atend_lock_val)
        winner_doc_lock = await client.get(f"lock:medico:{winner_doc_id}")
        assert winner_doc_lock == atendimento_id

        ttl = await client.ttl(k_atend_lock)
        assert 40 <= ttl <= 45


@pytest.mark.asyncio
async def test_doctor_active_lock_returns_0_conflict() -> None:
    """Verify doctor with ring or active consultation lock receives 0 / 409."""
    medico_id = uuid4()
    atendimento_id = uuid7()
    k_medico = f"lock:medico:{medico_id}"
    k_atend = f"lock:atendimento:{atendimento_id}"
    k_consulta = f"lock:consulta_ativa:medico:{medico_id}"
    k_fila = "fila:aptos"

    async for client in get_valkey_client():
        await client.set(k_medico, "active-call-id", ex=45)
        await client.zadd(k_fila, {str(atendimento_id): 1000})  # pyright: ignore[reportUnknownMemberType]

        manager = get_lua_script_manager()
        res = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico, k_atend, k_fila, k_consulta],
            args=[str(medico_id), str(atendimento_id), 45],
        )
        assert res == 0, "Expected code 0 when doctor has active ring lock"

        async with get_session_factory()() as session:
            service = build_alocacao_service_for_session(
                valkey=client,
                session=session,
            )
            cmd = AlocarChamadaCommand(
                medico_id=medico_id,
                atendimento_id=atendimento_id,
            )
            with pytest.raises(MedicoOcupadoError, match="já possui uma chamada"):
                await service.alocar_chamada(cmd)

        # Also test KEYS[4] (active consultation lock)
        await client.delete(k_medico)
        await client.set(k_consulta, "ongoing-consultation-id", ex=7200)
        res_consulta = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico, k_atend, k_fila, k_consulta],
            args=[str(medico_id), str(atendimento_id), 45],
        )
        assert res_consulta == 0, "Expected code 0 when lock:consulta_ativa exists"

        async with get_session_factory()() as session:
            service = build_alocacao_service_for_session(
                valkey=client,
                session=session,
            )
            with pytest.raises(MedicoOcupadoError, match="já possui uma chamada"):
                await service.alocar_proximo_paciente(medico_id=medico_id)


@pytest.mark.asyncio
async def test_alocar_chamada_sub_10ms_latency_benchmark() -> None:
    """Benchmark: assert script execution time on Valkey is < 10 ms (RNF-01)."""
    manager = get_lua_script_manager()
    k_fila = "fila:aptos"

    async for client in get_valkey_client():
        await manager.preload_scripts(client)
        latencies_ms: list[float] = []

        for i in range(50):
            atend_id = f"bench-atend-{i}"
            med_id = f"bench-med-{i}"
            k_med = f"lock:medico:{med_id}"
            k_atend = f"lock:atendimento:{atend_id}"
            k_consulta = f"lock:consulta_ativa:medico:{med_id}"

            await client.zadd(k_fila, {atend_id: 1000 + i})  # pyright: ignore[reportUnknownMemberType]

            start = time.perf_counter()
            res = await manager.execute_script(
                client=client,
                script_name="alocar_chamada",
                keys=[k_med, k_atend, k_fila, k_consulta],
                args=[med_id, atend_id, 45],
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies_ms.append(elapsed_ms)
            assert res == 1

        avg_latency = sum(latencies_ms) / len(latencies_ms)
        sorted_latencies = sorted(latencies_ms)
        p99_latency = sorted_latencies[int(len(sorted_latencies) * 0.98)]

        assert avg_latency < 10.0, (
            f"Expected average latency < 10ms, got {avg_latency:.2f}ms"
        )
        assert p99_latency < 20.0, (
            f"Expected p99 latency < 20ms, got {p99_latency:.2f}ms"
        )


@pytest.mark.asyncio
async def test_end_to_end_alocacao_service_with_postgres() -> None:
    """Verify end-to-end atomic allocation with PostgreSQL and Valkey consistency."""
    async with get_session_factory()() as session:
        sample_tcle_hash = (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        cenario = await seed_clinical_scenario(
            session,
            unidade_cnpj="88776655000144",
            unidade_razao_social="UBS Concurrency",
            paciente_cpf="33344455566",
            medico_cpf="77788899900",
            medico_email="dra.alocacao@ubs.gov.br",
            status_atendimento=StatusAtendimento.APTO_PARA_CHAMADA,
            tcle_hash=sample_tcle_hash,
        )
        medico = cenario.medico
        atendimento = cenario.atendimento
        atendimento.medico_id = None
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        atend_id = atendimento.id
        med_id = medico.id

        async for client in get_valkey_client():
            k_fila = "fila:aptos"
            await client.zadd(k_fila, {str(atend_id): 1000})  # pyright: ignore[reportUnknownMemberType]

            engine = build_queue_engine(valkey=client)
            service = build_alocacao_service_for_session(
                valkey=client,
                session=session,
                queue_engine=engine,
            )
            cmd = AlocarChamadaCommand(
                medico_id=med_id,
                atendimento_id=atend_id,
                ttl_segundos=45,
            )
            result = await service.alocar_chamada(cmd)

            assert result.atendimento_id == atend_id
            assert result.medico_id == med_id
            assert result.status == StatusAtendimento.CHAMANDO_PACIENTE.value
            assert result.ttl_segundos == 45

            reloaded = await session.get(Atendimento, atend_id)
            assert reloaded is not None
            assert reloaded.status == StatusAtendimento.CHAMANDO_PACIENTE.value
            assert reloaded.medico_id == med_id
            assert reloaded.chamada_iniciada_em is not None

            k_med = f"lock:medico:{med_id}"
            k_atend = f"lock:atendimento:{atend_id}"
            assert await client.get(k_med) == str(atend_id)
            assert await client.get(k_atend) == str(med_id)
            assert await client.zrank(k_fila, str(atend_id)) is None  # pyright: ignore[reportUnknownMemberType]

            await engine.liberar_ring(med_id, atend_id)
            assert await client.exists(k_med) == 0
            assert await client.exists(k_atend) == 0


@pytest.mark.asyncio
async def test_concurrent_10_doctors_alocar_proximo_no_false_409() -> None:
    """10 concurrent doctors calling /chamar-proximo allocate 10 distinct patients."""
    sample_tcle = "c" * 64
    medicos_ids: list[UUID] = []
    atendimentos_ids: list[UUID] = []

    async with get_session_factory()() as session:
        for i in range(10):
            pac = make_paciente(cpf=f"100000000{i:02d}", telefone=f"119000000{i:02d}")
            med = make_profissional(
                cpf=f"200000000{i:02d}",
                email=f"dr.concurrent{i}@ubs.gov.br",
                papel="MEDICO",
                crm=f"99{i:03d}",
                crm_uf="SP",
            )
            session.add_all([pac, med])
            await session.flush()

            atend = make_atendimento(
                paciente_id=pac.id,
                prioridade_clinica=3,
                tcle_hash=sample_tcle,
            )
            atend.promover_para_apto()
            session.add(atend)
            await session.flush()
            medicos_ids.append(med.id)
            atendimentos_ids.append(atend.id)

        await session.commit()

    async for client in get_valkey_client():
        for idx, aid in enumerate(atendimentos_ids):
            score = calcular_score(3) + idx
            await client.zadd("fila:aptos", {str(aid): score})  # pyright: ignore[reportUnknownMemberType]

        async def _call_next(doc_id: UUID, cl: Redis = client) -> UUID | None:
            async with get_session_factory()() as doc_session:
                fila_svc = build_fila_service_for_session(
                    session=doc_session,
                    valkey=cl,
                )
                res = await fila_svc.adquirir_proximo_paciente(
                    AdquirirProximoPacienteCommand(medico_id=doc_id, max_scan=50)
                )
                return res.atendimento_id if res is not None else None

        allocated = await asyncio.gather(*[_call_next(mid) for mid in medicos_ids])
        non_null = [aid for aid in allocated if aid is not None]

        assert len(non_null) == 10
        assert len(set(non_null)) == 10
        assert set(non_null) == set(atendimentos_ids)
        assert await client.zcard("fila:aptos") == 0  # pyright: ignore[reportUnknownMemberType]
