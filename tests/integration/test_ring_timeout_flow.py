"""Integration tests for deterministic 45s ring timeout end-to-end flow (RN02)."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from arq.connections import create_pool
from arq.worker import create_worker
from sqlalchemy import text
from src.core.context import tenant_context
from src.core.database import Base, async_session_factory, engine
from src.core.valkey import close_valkey_pool, get_valkey_client
from src.modules.queue.application.dtos import AlocarChamadaCommand
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager
from src.worker.settings import WorkerSettings

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento

_TEST_ORG_ID = 777


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
        keys = await client.keys(f"lock:{_TEST_ORG_ID}:*")  # pyright: ignore[reportUnknownMemberType]
        keys.extend(await client.keys(f"fila:{_TEST_ORG_ID}:*"))  # pyright: ignore[reportUnknownMemberType]
        keys.extend(await client.keys("arq:*"))  # pyright: ignore[reportUnknownMemberType]
        if keys:
            await client.delete(*keys)

    await close_valkey_pool()


@pytest.mark.asyncio
async def test_end_to_end_ring_timeout_releases_locks_and_marks_no_show() -> None:
    """Worker resolves no-show, marks attendance absent and frees doctor immediately."""
    org = make_organizacao(id=_TEST_ORG_ID)
    doctor = make_profissional(organizacao_id=org.id)
    patient = make_paciente(organizacao_id=org.id)

    atendimento = make_atendimento(
        organizacao_id=org.id,
        paciente_id=patient.id,
        medico_id=doctor.id,
        status=StatusAtendimento.CHAMANDO_PACIENTE.value,
        chamada_iniciada_em=datetime.now(UTC),
    )

    with tenant_context(org.id):
        async with async_session_factory() as session:
            session.add_all([org, doctor, patient, atendimento])
            await session.commit()

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
    org = make_organizacao(id=_TEST_ORG_ID)
    doctor = make_profissional(organizacao_id=org.id)
    patient = make_paciente(organizacao_id=org.id)

    atendimento = make_atendimento(
        organizacao_id=org.id,
        paciente_id=patient.id,
        medico_id=doctor.id,
        status=StatusAtendimento.EM_ATENDIMENTO.value,
        chamada_iniciada_em=datetime.now(UTC),
    )

    with tenant_context(org.id):
        async with async_session_factory() as session:
            session.add_all([org, doctor, patient, atendimento])
            await session.commit()

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
    org = make_organizacao(id=_TEST_ORG_ID)
    doctor = make_profissional(organizacao_id=org.id)
    patient = make_paciente(organizacao_id=org.id)

    atendimento = make_atendimento(
        organizacao_id=org.id,
        paciente_id=patient.id,
        status=StatusAtendimento.APTO_PARA_CHAMADA.value,
        data_entrada_fila=datetime.now(UTC),
    )

    with tenant_context(org.id):
        async with async_session_factory() as session:
            session.add_all([org, doctor, patient, atendimento])
            await session.commit()

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
