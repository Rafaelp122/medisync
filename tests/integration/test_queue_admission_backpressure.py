"""Integration tests for stochastic queue admission control and backpressure (RN05)."""

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from src.core.database import Base, async_session_factory, engine
from src.core.uuid7 import uuid7

if TYPE_CHECKING:
    from uuid import UUID

from src.core.valkey import close_valkey_pool, get_valkey_client
from src.modules.queue.application.dtos import (
    AdquirirProximoPacienteCommand,
    IngressarFilaComBackpressureCommand,
    IngressarFilaCommand,
)
from src.modules.queue.application.ports.queue_overflow_notifier import (
    QueueOverflowEvent,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import AdmissaoFilaSuspensaError
from src.modules.queue.domain.models import (
    PrioridadeClinica,
)
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento

SAMPLE_TCLE = "b" * 64


class SpyNotifier:
    """Spy notifier collecting emitted overflow events for assertions."""

    def __init__(self) -> None:
        self.events: list[QueueOverflowEvent] = []

    async def emitir_transbordo(self, event: QueueOverflowEvent) -> None:
        self.events.append(event)


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
        keys.extend(await client.keys("plantao:*"))  # pyright: ignore[reportUnknownMemberType]
        keys.extend(await client.keys("cota:*"))  # pyright: ignore[reportUnknownMemberType]
        if keys:
            await client.delete(*keys)

    await close_valkey_pool()


@pytest.mark.asyncio
async def test_acceptance_criteria_backpressure_rejection_and_queue_preservation() -> (
    None
):
    """Test criteria 1 & 2: Safe rejection while preserving in-flight queue."""
    org_id = 201
    spy_notifier = SpyNotifier()

    async for valkey in get_valkey_client():
        async with async_session_factory() as session:
            # 1. Setup DB: 1 org, 1 doctor, 5 patients already in queue
            org = make_organizacao(
                cnpj="99887766000155", razao_social="UBS Backpressure"
            )
            session.add(org)
            await session.commit()
            await session.refresh(org)
            org_id = org.id

            medico = make_profissional(
                org_id,
                cpf="11122233344",
                email="dr.shift@ubs.gov.br",
                papel="MEDICO",
            )
            session.add(medico)
            await session.commit()
            await session.refresh(medico)

            # Ingest 5 existing patients into the queue
            controle = ControleAdmissaoService(valkey=valkey, notifier=spy_notifier)
            alocacao = AlocacaoChamadaService(
                valkey=valkey,
                db_session=session,
                lua_manager=get_lua_script_manager(),
            )
            service = FilaService(
                valkey=valkey,
                db_session=session,
                alocacao_service=alocacao,
                controle_admissao=controle,
            )

            existing_ids: list[UUID] = []
            for i in range(5):
                p = make_paciente(org_id, cpf=f"1234567890{i}")
                session.add(p)
                await session.commit()
                await session.refresh(p)

                atend = make_atendimento(
                    organizacao_id=org_id,
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
                        organizacao_id=org_id,
                        atendimento_id=atend.id,
                        prioridade_clinica=atend.prioridade_clinica,
                    )
                )

            # Confirm 5 patients in queue
            assert await service.obter_tamanho_fila(org_id) == 5

            # 2. Attempt to admit 6th patient with tight capacity:
            # 5 waiting * 600s TMA * 1.25 alpha / 1 doctor = 3750s workload
            # Remaining shift = 1800s (30 min) -> 3750s > 1800s -> BACKPRESSURE!
            new_patient_id = uuid7()
            blocked_cmd = IngressarFilaComBackpressureCommand(
                organizacao_id=org_id,
                atendimento_id=new_patient_id,
                prioridade_clinica=PrioridadeClinica.URGENTE,
                medicos_ativos=1,
                tempo_restante_segundos=1800,
                tma_estimado_segundos=600,
                alpha_margem=1.25,
            )

            with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
                await service.admitir_com_backpressure(blocked_cmd)

            # AC 1: Rejected with HTTP 503 and polite explanation
            assert exc_info.value.status_code == 503
            assert exc_info.value.motivo == "CAPACIDADE_EXCEDIDA"
            assert "capacidade do plantão atual foi atingida" in exc_info.value.detail

            # AC 2: Invariante de Transbordo -> existing 5 patients are NEVER dropped!
            assert await service.obter_tamanho_fila(org_id) == 5
            current_queue = await service.listar_fila(org_id)
            assert current_queue == [str(item_id) for item_id in existing_ids]

            # Doctor can still call and serve existing patients without interruption
            res_call = await service.adquirir_proximo_paciente(
                AdquirirProximoPacienteCommand(
                    organizacao_id=org_id,
                    medico_id=medico.id,
                )
            )
            assert res_call is not None
            assert res_call.atendimento_id == existing_ids[0]
            assert await service.obter_tamanho_fila(org_id) == 4


@pytest.mark.asyncio
async def test_acceptance_criterion_3_queue_overflow_transit_event_emitted() -> None:
    """Test criterion 3: QUEUE_OVERFLOW_TRANSIT event has full telemetry."""
    org_id = 202
    spy_notifier = SpyNotifier()

    async for valkey in get_valkey_client():
        async with async_session_factory() as session:
            controle = ControleAdmissaoService(valkey=valkey, notifier=spy_notifier)
            service = FilaService(
                valkey=valkey,
                db_session=session,
                controle_admissao=controle,
            )

            # Seed 8 patients in queue
            for _ in range(8):
                await service.ingressar_fila(
                    IngressarFilaCommand(
                        organizacao_id=org_id,
                        atendimento_id=uuid7(),
                        prioridade_clinica=PrioridadeClinica.URGENTE,
                    )
                )

            # Attempt admission: 8 * 600 * 1.25 / 2 = 3000s > 2000s
            blocked_cmd = IngressarFilaComBackpressureCommand(
                organizacao_id=org_id,
                atendimento_id=uuid7(),
                prioridade_clinica=PrioridadeClinica.URGENTE,
                medicos_ativos=2,
                tempo_restante_segundos=2000,
                tma_estimado_segundos=600,
                alpha_margem=1.25,
            )

            with pytest.raises(AdmissaoFilaSuspensaError):
                await service.admitir_com_backpressure(blocked_cmd)

            # AC 3: Exactly 1 QUEUE_OVERFLOW_TRANSIT event was emitted
            assert len(spy_notifier.events) == 1
            ev = spy_notifier.events[0]

            assert ev.evento == "QUEUE_OVERFLOW_TRANSIT"
            assert ev.organizacao_id == org_id
            assert ev.motivo == "CAPACIDADE_EXCEDIDA"
            assert ev.pacientes_aguardando == 8
            assert ev.medicos_ativos == 2
            assert ev.carga_estimada_segundos == 3000.0
            assert ev.tempo_restante_segundos == 2000.0
            assert ev.alpha_utilizado == 1.25
            assert "capacidade do plantão atual foi atingida" in ev.mensagem_orientacao
            assert isinstance(ev.disparado_em, datetime)


@pytest.mark.asyncio
async def test_rejection_no_active_doctors_emits_event() -> None:
    """Zero active doctors blocks admission and emits overflow event."""
    org_id = 203
    spy_notifier = SpyNotifier()

    async for valkey in get_valkey_client():
        async with async_session_factory() as session:
            controle = ControleAdmissaoService(valkey=valkey, notifier=spy_notifier)
            service = FilaService(
                valkey=valkey,
                db_session=session,
                controle_admissao=controle,
            )

            cmd = IngressarFilaComBackpressureCommand(
                organizacao_id=org_id,
                atendimento_id=uuid7(),
                prioridade_clinica=PrioridadeClinica.URGENTE,
                medicos_ativos=0,
                tempo_restante_segundos=3600,
            )

            with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
                await service.admitir_com_backpressure(cmd)

            assert exc_info.value.motivo == "SEM_MEDICOS_ATIVOS"
            assert "não há médicos plantonistas ativos" in exc_info.value.detail
            assert len(spy_notifier.events) == 1
            assert spy_notifier.events[0].motivo == "SEM_MEDICOS_ATIVOS"


@pytest.mark.asyncio
async def test_rejection_daily_quota_reached_emits_event() -> None:
    """Reaching daily max quota blocks admission and emits overflow event."""
    org_id = 204
    spy_notifier = SpyNotifier()

    async for valkey in get_valkey_client():
        async with async_session_factory() as session:
            controle = ControleAdmissaoService(valkey=valkey, notifier=spy_notifier)
            service = FilaService(
                valkey=valkey,
                db_session=session,
                controle_admissao=controle,
            )

            cmd = IngressarFilaComBackpressureCommand(
                organizacao_id=org_id,
                atendimento_id=uuid7(),
                prioridade_clinica=PrioridadeClinica.URGENTE,
                medicos_ativos=5,
                tempo_restante_segundos=10000,
                total_admissoes_hoje=300,
                cota_diaria_maxima=300,
            )

            with pytest.raises(AdmissaoFilaSuspensaError) as exc_info:
                await service.admitir_com_backpressure(cmd)

            assert exc_info.value.motivo == "COTA_ATINGIDA"
            assert "cota diária de atendimentos da unidade" in exc_info.value.detail
            assert len(spy_notifier.events) == 1
            assert spy_notifier.events[0].motivo == "COTA_ATINGIDA"
