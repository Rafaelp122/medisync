"""Integration tests for stochastic queue admission control and backpressure (RN05)."""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from src.core.database import get_session_factory
from src.core.valkey import get_valkey_client

if TYPE_CHECKING:
    from uuid import UUID

from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdquirirProximoPacienteCommand,
    IngressarFilaCommand,
)
from src.modules.queue.composition import (
    build_fila_service_for_session,
    build_queue_engine,
)
from src.modules.queue.domain.exceptions import AdmissaoFilaSuspensaError
from src.modules.queue.domain.models import PrioridadeClinica
from src.modules.queue.infrastructure.valkey_queue_engine import FILA_APTOS_KEY
from src.modules.telemetry.domain.models import ConfiguracaoPlantao

from tests.factories.identity import make_paciente, make_profissional
from tests.factories.queue import make_atendimento

SAMPLE_TCLE = "b" * 64

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_acceptance_criteria_backpressure_rejection_and_queue_preservation() -> (
    None
):
    """Safe rejection preserves in-flight queue and rolls back reserved quota."""
    async for valkey in get_valkey_client():
        async with get_session_factory()() as session:
            medico = make_profissional(
                cpf="11122233344",
                email="dr.shift@ubs.gov.br",
                papel="MEDICO",
            )
            session.add(medico)
            await session.commit()
            await session.refresh(medico)
            medico_id = medico.id

            engine = build_queue_engine(valkey=valkey)
            await engine.registrar_medico_ativo(medico_id)
            service = build_fila_service_for_session(session=session, valkey=valkey)

            existing_ids: list[UUID] = []
            for i in range(5):
                p = make_paciente(cpf=f"1234567890{i}", telefone=f"1198765430{i}")
                session.add(p)
                await session.commit()
                await session.refresh(p)

                atend = make_atendimento(
                    paciente_id=p.id,
                    prioridade_clinica=PrioridadeClinica.URGENTE,
                    tcle_hash=SAMPLE_TCLE,
                )
                atend.promover_para_apto()
                session.add(atend)
                await session.commit()
                await session.refresh(atend)
                existing_ids.append(atend.id)

                await service.ingressar_fila(
                    IngressarFilaCommand(
                        atendimento_id=atend.id,
                        prioridade_clinica=atend.prioridade_clinica,
                    )
                )

            assert await service.obter_tamanho_fila() == 5

            new_patient = make_paciente(cpf="99900011122", telefone="11999998888")
            session.add(new_patient)
            await session.commit()
            await session.refresh(new_patient)

            # 5 waiting * 600s TMA * 1.25 alpha / 1 active doctor = 3750s > 1800s
            blocked_cmd = AdmissaoAtendimentoCommand(
                paciente_id=new_patient.id,
                queixa_principal="Dor de cabeça leve",
                sintomas=[],
                tcle_hash=SAMPLE_TCLE,
                tempo_restante_segundos=1800,
                tma_estimado_segundos=600,
                alpha_margem=1.25,
            )

            with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
                await service.admitir_paciente(blocked_cmd)

            assert exc_info.value.status_code == 503
            assert exc_info.value.motivo == "CAPACIDADE_EXCEDIDA"
            assert "capacidade do plantão atual foi atingida" in exc_info.value.detail

            # Quota reservation was rolled back atomically
            today_key = f"queue:admissoes:{datetime.now(UTC).strftime('%Y-%m-%d')}"
            assert await valkey.get(today_key) == "0"

            # Existing 5 patients are preserved untouched
            assert await service.obter_tamanho_fila() == 5
            current_queue: list[str] = await valkey.zrange(FILA_APTOS_KEY, 0, -1)  # pyright: ignore[reportUnknownMemberType]
            assert current_queue == [str(item_id) for item_id in existing_ids]

            res_call = await service.adquirir_proximo_paciente(
                AdquirirProximoPacienteCommand(medico_id=medico_id)
            )
            assert res_call is not None
            assert res_call.atendimento_id == existing_ids[0]
            assert await service.obter_tamanho_fila() == 4


@pytest.mark.asyncio
async def test_acceptance_criterion_3_queue_overflow_transit_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Overflow emits structured warning with active doctors and workload."""
    async for valkey in get_valkey_client():
        async with get_session_factory()() as session:
            engine = build_queue_engine(valkey=valkey)
            for idx in range(2):
                doc = make_profissional(
                    cpf=f"2223334440{idx}",
                    email=f"dr{idx}@ubs.gov.br",
                    papel="MEDICO",
                )
                session.add(doc)
                await session.commit()
                await engine.registrar_medico_ativo(doc.id)

            patient = make_paciente(cpf="88877766655", telefone="11977776666")
            session.add(patient)
            await session.commit()

            service = build_fila_service_for_session(session=session, valkey=valkey)
            for _ in range(8):
                await service.ingressar_fila(
                    IngressarFilaCommand(
                        atendimento_id=make_atendimento(
                            paciente_id=patient.id,
                            prioridade_clinica=PrioridadeClinica.URGENTE,
                            tcle_hash=SAMPLE_TCLE,
                        ).id,
                        prioridade_clinica=PrioridadeClinica.URGENTE,
                    )
                )

            # 8 * 600 * 1.25 / 2 active doctors = 3000s > 2000s
            blocked_cmd = AdmissaoAtendimentoCommand(
                paciente_id=patient.id,
                queixa_principal="Coriza",
                sintomas=[],
                tcle_hash=SAMPLE_TCLE,
                tempo_restante_segundos=2000,
                tma_estimado_segundos=600,
                alpha_margem=1.25,
            )

            admissao_logger = logging.getLogger("medisync.queue.admissao")
            prev_disabled = admissao_logger.disabled
            admissao_logger.disabled = False
            admissao_logger.addHandler(caplog.handler)
            try:
                with (
                    caplog.at_level(logging.WARNING, logger="medisync.queue.admissao"),
                    pytest.raises(AdmissaoFilaSuspensaError),
                ):
                    await service.admitir_paciente(blocked_cmd)
            finally:
                admissao_logger.removeHandler(caplog.handler)
                admissao_logger.disabled = prev_disabled

            assert "CAPACIDADE_EXCEDIDA" in caplog.text
            assert "3000.0s" in caplog.text


@pytest.mark.asyncio
async def test_rejection_no_active_doctors_blocks_admission() -> None:
    """Zero active doctors in Valkey blocks admission with SEM_MEDICOS_ATIVOS."""
    async for valkey in get_valkey_client():
        async with get_session_factory()() as session:
            patient = make_paciente(cpf="77766655544", telefone="11966665555")
            session.add(patient)
            await session.commit()

            service = build_fila_service_for_session(session=session, valkey=valkey)
            cmd = AdmissaoAtendimentoCommand(
                paciente_id=patient.id,
                queixa_principal="Cefaleia",
                sintomas=[],
                tcle_hash=SAMPLE_TCLE,
                tempo_restante_segundos=3600,
            )

            with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
                await service.admitir_paciente(cmd)

            assert exc_info.value.motivo == "SEM_MEDICOS_ATIVOS"
            assert "não há médicos plantonistas ativos" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rejection_daily_quota_from_config_plantao_blocks_and_preserves_cap() -> (
    None
):
    """Persisted ConfiguracaoPlantao quota blocks overflow atomically in Valkey."""
    async for valkey in get_valkey_client():
        async with get_session_factory()() as session:
            config = ConfiguracaoPlantao(
                alpha_backpressure=1.25,
                cota_diaria_maxima=1,
                tma_padrao_segundos=600,
                tempo_tolerancia_ring_segundos=45,
            )
            doc = make_profissional(
                cpf="55544433322",
                email="dr.quota@ubs.gov.br",
                papel="MEDICO",
            )
            patient = make_paciente(cpf="66655544433", telefone="11955554444")
            session.add_all([config, doc, patient])
            await session.commit()

            engine = build_queue_engine(valkey=valkey)
            await engine.registrar_medico_ativo(doc.id)
            service = build_fila_service_for_session(session=session, valkey=valkey)

            first = await service.admitir_paciente(
                AdmissaoAtendimentoCommand(
                    paciente_id=patient.id,
                    queixa_principal="Febre leve",
                    sintomas=["febre"],
                    tcle_hash=SAMPLE_TCLE,
                )
            )
            assert first.atendimento_id is not None

            with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
                await service.admitir_paciente(
                    AdmissaoAtendimentoCommand(
                        paciente_id=patient.id,
                        queixa_principal="Dor leve",
                        sintomas=[],
                        tcle_hash=SAMPLE_TCLE,
                    )
                )

            assert exc_info.value.motivo == "COTA_ATINGIDA"
            assert "cota diária de atendimentos da unidade" in exc_info.value.detail
            today_key = f"queue:admissoes:{datetime.now(UTC).strftime('%Y-%m-%d')}"
            assert await valkey.get(today_key) == "1"
