"""Integration tests for unified admission and ARQ eligibility (Issue #52)."""

import pytest
from arq.connections import create_pool
from arq.worker import create_worker
from src.core.context import tenant_context
from src.core.database import async_session_factory
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdmissaoAtendimentoResult,
)
from src.modules.queue.composition import build_fila_service_for_session
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.triage.domain.exceptions import EmergenciaCriticaSamuError
from src.modules.triage.domain.models.triagem import Triagem
from src.modules.triage.infrastructure.adapters.samu_emergency_notifier_adapter import (
    SamuEmergencyNotifierAdapter,
)
from src.worker.settings import WorkerSettings

from tests.factories.identity import make_organizacao, make_paciente

_TEST_ORG_ID = 888

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_admissao_integrada_persists_both_models_and_enqueues_arq_job() -> None:
    """Patient intake persists models 1:1 and enqueues ARQ eligibility."""
    org = make_organizacao(id=_TEST_ORG_ID, modo_publico_sus=True)
    patient = make_paciente(organizacao_id=org.id)

    with tenant_context(org.id):
        async with async_session_factory() as session:
            session.add_all([org, patient])
            await session.commit()

    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        with tenant_context(org.id):
            async with async_session_factory() as session:
                service = build_fila_service_for_session(
                    session=session,
                    valkey=pool,
                    arq_pool=pool,
                )
                cmd = AdmissaoAtendimentoCommand(
                    organizacao_id=org.id,
                    paciente_id=patient.id,
                    queixa_principal="Febre moderada e dor de cabeça há 2 dias",
                    sintomas=["febre", "cefaleia"],
                    escala_dor=4,
                    tcle_texto="Termo de consentimento para consulta telemedicina",
                    medicos_ativos=2,
                )
                result = await service.admitir_paciente(cmd)

                assert isinstance(result, AdmissaoAtendimentoResult)
                assert (
                    result.status_atendimento
                    == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
                )
                assert result.alerta_samu_disparado is False

        # 1. Verify DB persistence of Atendimento
        with tenant_context(org.id):
            async with async_session_factory() as session:
                atend = await session.get(Atendimento, result.atendimento_id)
                assert atend is not None
                assert (
                    atend.status
                    == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
                )
                assert atend.paciente_id == patient.id

                # 2. Verify DB persistence of Triagem (1:1 with Atendimento)
                triagem = await session.get(Triagem, result.triagem_id)
                assert triagem is not None
                assert triagem.atendimento_id == atend.id
                assert triagem.prioridade_calculada in (3, 4)
                assert triagem.alerta_samu_disparado is False

        # 3. Verify ARQ eligibility job was enqueued in Valkey
        job_key = f"arq:job:elegibilidade:{result.atendimento_id}"
        exists = await pool.exists(job_key)
        assert exists == 1

        # 4. Execute ARQ worker in burst mode to promote to APTO_PARA_CHAMADA
        worker = create_worker(
            WorkerSettings,  # pyright: ignore[reportArgumentType]
            redis_pool=pool,
            burst=True,
        )
        await worker.main()

        # 5. Verify attendance promoted to APTO and ingested into Valkey ZSET
        with tenant_context(org.id):
            async with async_session_factory() as session:
                refreshed_atend = await session.get(Atendimento, result.atendimento_id)
                assert refreshed_atend is not None
                assert (
                    refreshed_atend.status == StatusAtendimento.APTO_PARA_CHAMADA.value
                )

        k_fila = f"fila:{org.id}:aptos"
        score = await pool.zscore(k_fila, str(result.atendimento_id))
        assert score is not None
        assert score > 0
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_admissao_integrada_emergencia_samu_dispatches_alert_and_blocks_db() -> (
    None
):
    """Critical emergency alerts SAMU and does not persist Atendimento."""
    org = make_organizacao(id=_TEST_ORG_ID, modo_publico_sus=False)
    patient = make_paciente(organizacao_id=org.id)

    with tenant_context(org.id):
        async with async_session_factory() as session:
            session.add_all([org, patient])
            await session.commit()

    samu_notifier = SamuEmergencyNotifierAdapter()
    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        from src.modules.triage.composition import build_triage_service_for_session

        with tenant_context(org.id):
            async with async_session_factory() as session:
                triage_svc = build_triage_service_for_session(
                    session=session,
                    notifier=samu_notifier,
                )
                service = build_fila_service_for_session(
                    session=session,
                    valkey=pool,
                    triage_port=triage_svc,
                    arq_pool=pool,
                )
                cmd = AdmissaoAtendimentoCommand(
                    organizacao_id=org.id,
                    paciente_id=patient.id,
                    queixa_principal="Paciente inconsciente sem respirar e em choque",
                    sintomas=["inconsciencia"],
                    escala_dor=10,
                    tcle_texto="Termo de consentimento aceito",
                )

                with pytest.raises(EmergenciaCriticaSamuError):
                    await service.admitir_paciente(cmd)

        # Verify SAMU alert was dispatched
        assert len(samu_notifier.sent_alerts) == 1
        alert = samu_notifier.sent_alerts[0]
        assert alert.organizacao_id == org.id
        assert "inconsciencia" in alert.sintomas_alerta

        # Verify no Atendimento was created in DB for this patient
        with tenant_context(org.id):
            async with async_session_factory() as session:
                from sqlalchemy import select

                stmt = select(Atendimento).where(Atendimento.paciente_id == patient.id)
                atendimentos = (await session.execute(stmt)).scalars().all()
                assert len(atendimentos) == 0
    finally:
        await pool.aclose()
