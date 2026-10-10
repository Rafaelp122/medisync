"""Integration tests for deterministic 45s ring timeout end-to-end flow (RN02)."""

from datetime import UTC, datetime

import pytest
from arq.connections import create_pool
from arq.worker import create_worker
from src.core.context import tenant_context
from src.core.database import async_session_factory
from src.modules.queue.application.dtos import AlocarChamadaCommand
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager
from src.worker.settings import WorkerSettings

from tests.factories.scenarios import seed_clinical_scenario

_TEST_ORG_ID = 777

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_end_to_end_ring_timeout_releases_locks_and_marks_no_show() -> None:
    """Worker resolves no-show, marks attendance absent and frees doctor immediately."""
    with tenant_context(_TEST_ORG_ID):
        async with async_session_factory() as session:
            cenario = await seed_clinical_scenario(
                session,
                org_id=_TEST_ORG_ID,
                status_atendimento=StatusAtendimento.CHAMANDO_PACIENTE,
            )
            cenario.atendimento.chamada_iniciada_em = datetime.now(UTC)
            session.add(cenario.atendimento)
            await session.commit()
            org = cenario.organizacao
            doctor = cenario.medico
            atendimento = cenario.atendimento

    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        k_medico = f"lock:{org.id}:medico:{doctor.id}"
        k_atend = f"lock:{org.id}:atendimento:{atendimento.id}"
        await pool.set(k_medico, str(atendimento.id), ex=45)
        await pool.set(k_atend, str(doctor.id), ex=45)

        # Enqueue the timeout resolution job
        job = await pool.enqueue_job(
            "resolver_ring_timeout_task",
            organizacao_id=org.id,
            atendimento_id=str(atendimento.id),
            medico_id=str(doctor.id),
        )
        assert job is not None

        # Execute worker in burst mode
        worker = create_worker(
            WorkerSettings,  # pyright: ignore[reportArgumentType]
            burst=True,
            redis_pool=pool,
        )
        await worker.main()

        assert worker.jobs_complete >= 1

        # 1. Verify PostgreSQL persistence: state must be PACIENTE_AUSENTE
        with tenant_context(org.id):
            async with async_session_factory() as session:
                refreshed = await session.get(Atendimento, atendimento.id)
                assert refreshed is not None
                assert refreshed.status == StatusAtendimento.PACIENTE_AUSENTE.value
                assert refreshed.chamada_finalizada_em is not None

        # 2. Verify Valkey locks: both locks must be completely deleted
        medico_lock_exists = await pool.exists(k_medico)
        atend_lock_exists = await pool.exists(k_atend)
        assert medico_lock_exists == 0
        assert atend_lock_exists == 0
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_end_to_end_answered_call_promotes_active_consultation_lock() -> None:
    """When patient answers in time, worker preserves call and promotes lock."""
    with tenant_context(_TEST_ORG_ID):
        async with async_session_factory() as session:
            cenario = await seed_clinical_scenario(
                session,
                org_id=_TEST_ORG_ID,
                status_atendimento=StatusAtendimento.EM_ATENDIMENTO,
            )
            cenario.atendimento.chamada_iniciada_em = datetime.now(UTC)
            session.add(cenario.atendimento)
            await session.commit()
            org = cenario.organizacao
            doctor = cenario.medico
            atendimento = cenario.atendimento

    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        k_medico = f"lock:{org.id}:medico:{doctor.id}"
        k_atend = f"lock:{org.id}:atendimento:{atendimento.id}"
        k_consulta = f"lock:{org.id}:consulta_ativa:medico:{doctor.id}"
        await pool.set(k_medico, str(atendimento.id), ex=45)
        await pool.set(k_atend, str(doctor.id), ex=45)

        # Enqueue the timeout resolution job
        job = await pool.enqueue_job(
            "resolver_ring_timeout_task",
            organizacao_id=org.id,
            atendimento_id=str(atendimento.id),
            medico_id=str(doctor.id),
        )
        assert job is not None

        # Execute worker in burst mode
        worker = create_worker(
            WorkerSettings,  # pyright: ignore[reportArgumentType]
            burst=True,
            redis_pool=pool,
        )
        await worker.main()

        # 1. Verify PostgreSQL persistence: state must remain EM_ATENDIMENTO
        with tenant_context(org.id):
            async with async_session_factory() as session:
                refreshed = await session.get(Atendimento, atendimento.id)
                assert refreshed is not None
                assert refreshed.status == StatusAtendimento.EM_ATENDIMENTO.value

        # 2. Verify active consultation lock is promoted in Valkey with TTL
        consulta_lock_exists = await pool.exists(k_consulta)
        assert consulta_lock_exists == 1
        ttl = await pool.ttl(k_consulta)
        assert ttl > 0

        # Ring locks are discarded
        assert await pool.exists(k_medico) == 0
        assert await pool.exists(k_atend) == 0
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_alocar_chamada_schedules_arq_job_in_valkey() -> None:
    """alocar_chamada service schedules deferred job with deduplicated ID in Valkey."""
    with tenant_context(_TEST_ORG_ID):
        async with async_session_factory() as session:
            cenario = await seed_clinical_scenario(
                session,
                org_id=_TEST_ORG_ID,
                status_atendimento=StatusAtendimento.APTO_PARA_CHAMADA,
            )
            cenario.atendimento.medico_id = None
            cenario.atendimento.data_entrada_fila = datetime.now(UTC)
            session.add(cenario.atendimento)
            await session.commit()
            org = cenario.organizacao
            doctor = cenario.medico
            atendimento = cenario.atendimento

    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        # Push to Valkey queue
        k_fila = f"fila:{org.id}:aptos"
        await pool.zadd(k_fila, {str(atendimento.id): 100.0})

        with tenant_context(org.id):
            async with async_session_factory() as session:
                service = AlocacaoChamadaService(
                    valkey=pool,
                    db_session=session,
                    lua_manager=get_lua_script_manager(),
                    arq_pool=pool,
                )
                cmd = AlocarChamadaCommand(
                    organizacao_id=org.id,
                    medico_id=doctor.id,
                    atendimento_id=atendimento.id,
                    ttl_segundos=45,
                )
                res = await service.alocar_chamada(cmd)
                assert res.atendimento_id == atendimento.id

        # Verify deferred job was enqueued in ARQ queue with expected job_id
        job_key = f"arq:job:ring_timeout:{atendimento.id}"
        exists = await pool.exists(job_key)
        assert exists == 1
    finally:
        await pool.aclose()
