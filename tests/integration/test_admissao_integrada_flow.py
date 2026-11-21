"""Integration tests for unified admission and ARQ eligibility (Issue #52)."""

import pytest
from arq.connections import create_pool
from sqlalchemy import select
from src.core.database import get_session_factory
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdmissaoAtendimentoResult,
)
from src.modules.queue.composition import build_fila_service_for_session
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.triage.composition import build_triage_service_for_session
from src.modules.triage.domain.exceptions import EmergenciaCriticaSamuError
from src.modules.triage.domain.models.triagem import Triagem
from src.modules.triage.infrastructure.adapters.samu_emergency_notifier_adapter import (
    SamuEmergencyNotifierAdapter,
)
from src.worker.settings import WorkerSettings

from tests.factories.identity import make_configuracao_unidade, make_paciente

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_admissao_integrada_persists_both_models_and_enqueues_arq_job() -> None:
    """Patient intake persists models 1:1 and enqueues ARQ eligibility."""
    unidade = make_configuracao_unidade(modo_publico_sus=True)
    patient = make_paciente()

    async with get_session_factory()() as session:
        session.add_all([unidade, patient])
        await session.commit()

    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        async with get_session_factory()() as session:
            service = build_fila_service_for_session(
                session=session,
                valkey=pool,
                arq_pool=pool,
            )
            cmd = AdmissaoAtendimentoCommand(
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
                result.status_atendimento == StatusAtendimento.APTO_PARA_CHAMADA.value
            )
            assert result.alerta_samu_disparado is False
            assert result.tcle_hash is not None
            assert len(result.tcle_hash) == 64

        # 1. Verify DB persistence of Atendimento
        async with get_session_factory()() as session:
            atend = await session.get(Atendimento, result.atendimento_id)
            assert atend is not None
            assert atend.tcle_hash == result.tcle_hash
            assert atend.status == StatusAtendimento.APTO_PARA_CHAMADA.value
            assert atend.paciente_id == patient.id

            # 2. Verify DB persistence of Triagem (1:1 with Atendimento)
            triagem = await session.get(Triagem, result.triagem_id)
            assert triagem is not None
            assert triagem.atendimento_id == atend.id
            assert triagem.prioridade_calculada in (3, 4)
            assert triagem.alerta_samu_disparado is False

        k_fila = "fila:aptos"
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
    unidade = make_configuracao_unidade(modo_publico_sus=False)
    patient = make_paciente()

    async with get_session_factory()() as session:
        session.add_all([unidade, patient])
        await session.commit()

    samu_notifier = SamuEmergencyNotifierAdapter()
    pool = await create_pool(WorkerSettings.redis_settings)
    try:
        async with get_session_factory()() as session:
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
        assert "inconsciencia" in alert.sintomas_alerta

        # Verify no Atendimento was created in DB for this patient
        async with get_session_factory()() as session:
            stmt = select(Atendimento).where(Atendimento.paciente_id == patient.id)
            atendimentos = (await session.execute(stmt)).scalars().all()
            assert len(atendimentos) == 0
    finally:
        await pool.aclose()
