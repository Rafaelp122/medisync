"""Integration tests for SUS & ambulatory eligibility and queue promotion (RF-02)."""

from collections.abc import AsyncGenerator

import pytest
from src.core.database import get_session_factory
from src.core.valkey import get_valkey_client
from src.modules.ambulatory import (
    ElegibilidadeService,
    RequisicaoElegibilidade,
    ResultadoElegibilidade,
    StatusElegibilidade,
)
from src.modules.ambulatory.composition import build_elegibilidade_service
from src.modules.queue.composition import build_fila_service_for_session
from src.modules.queue.domain.models import Atendimento, PrioridadeClinica
from src.modules.queue.domain.models.atendimento import StatusAtendimento

from tests.doubles import FakeElegibilidadeNotifier, FakeEligibilityProvider
from tests.factories.identity import make_configuracao_unidade, make_paciente
from tests.factories.queue import make_atendimento

_VALID_TCLE_HASH = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"


@pytest.fixture(autouse=True)
async def clean_database_and_valkey() -> AsyncGenerator[None, None]:
    """Ensure clean PostgreSQL tables and Valkey keys for each test."""
    from tests.helpers import clean_database_and_valkey as _clean

    await _clean()
    yield
    await _clean()


@pytest.mark.asyncio
async def test_end_to_end_sus_eligibility_flow() -> None:
    """Public SUS instance qualifies instantly and promotes attendance to ZSET."""
    unidade = make_configuracao_unidade(modo_publico_sus=True)
    patient = make_paciente()
    atend = make_atendimento(
        paciente_id=patient.id,
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value,
        prioridade_clinica=PrioridadeClinica.MUITO_URGENTE,
        tcle_hash=_VALID_TCLE_HASH,
    )

    async with get_session_factory()() as session:
        session.add_all([unidade, patient, atend])
        await session.commit()

    elegibilidade_svc = build_elegibilidade_service()
    resultado = await elegibilidade_svc.avaliar_elegibilidade(
        RequisicaoElegibilidade(
            atendimento_id=atend.id,
            paciente_id=patient.id,
            cns="123456789012345",
        )
    )
    assert resultado.aprovado is True
    assert resultado.codigo_autorizacao == "SUS-ISENTO"

    async for valkey in get_valkey_client():
        async with get_session_factory()() as session:
            fila_service = build_fila_service_for_session(
                session=session,
                valkey=valkey,
            )
            promocao = await fila_service.admitir_atendimento_apto(
                atend.id,
                codigo_autorizacao=resultado.codigo_autorizacao,
            )
            assert promocao.promovido is True
            assert promocao.status == "aprovado"

        async with get_session_factory()() as verify_session:
            refreshed = await verify_session.get(Atendimento, atend.id)
            assert refreshed is not None
            assert refreshed.status == StatusAtendimento.APTO_PARA_CHAMADA.value

        score = await valkey.zscore("fila:aptos", str(atend.id))  # pyright: ignore[reportUnknownMemberType]
        assert score is not None
        assert score > 0


@pytest.mark.asyncio
async def test_end_to_end_eligibility_approved_promotes_attendance() -> None:
    """Approved eligibility provider promotes attendance and ingests in queue."""
    patient = make_paciente()
    atend = make_atendimento(
        paciente_id=patient.id,
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_VALID_TCLE_HASH,
    )

    async with get_session_factory()() as session:
        session.add_all([patient, atend])
        await session.commit()

    fake_provider = FakeEligibilityProvider(
        ResultadoElegibilidade(
            aprovado=True,
            status=StatusElegibilidade.APROVADO,
            codigo_autorizacao="SUS-CADSUS-77",
        )
    )
    service = ElegibilidadeService(provider=fake_provider)
    resultado = await service.avaliar_elegibilidade(
        RequisicaoElegibilidade(
            atendimento_id=atend.id,
            paciente_id=patient.id,
        )
    )
    assert resultado.aprovado is True

    async for valkey in get_valkey_client():
        async with get_session_factory()() as session:
            fila_service = build_fila_service_for_session(
                session=session,
                valkey=valkey,
            )
            promocao = await fila_service.admitir_atendimento_apto(
                atend.id,
                codigo_autorizacao=resultado.codigo_autorizacao,
            )
            assert promocao.promovido is True

        async with get_session_factory()() as verify_session:
            refreshed = await verify_session.get(Atendimento, atend.id)
            assert refreshed is not None
            assert refreshed.status == StatusAtendimento.APTO_PARA_CHAMADA.value

        score = await valkey.zscore("fila:aptos", str(atend.id))  # pyright: ignore[reportUnknownMemberType]
        assert score is not None


@pytest.mark.asyncio
async def test_end_to_end_eligibility_rejected_preserves_queue_position() -> None:
    """Rejection notifies waiting room and leaves attendance retained (RF-05)."""
    patient = make_paciente()
    atend = make_atendimento(
        paciente_id=patient.id,
        status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value,
        prioridade_clinica=PrioridadeClinica.URGENTE,
        tcle_hash=_VALID_TCLE_HASH,
    )

    async with get_session_factory()() as session:
        session.add_all([patient, atend])
        await session.commit()

    fake_provider = FakeEligibilityProvider(
        ResultadoElegibilidade(
            aprovado=False,
            status=StatusElegibilidade.REJEITADO,
            motivo="Divergência cadastral CADSUS",
        )
    )
    fake_notifier = FakeElegibilidadeNotifier()
    service = ElegibilidadeService(provider=fake_provider, notifier=fake_notifier)

    resultado = await service.avaliar_elegibilidade(
        RequisicaoElegibilidade(
            atendimento_id=atend.id,
            paciente_id=patient.id,
        )
    )

    assert resultado.aprovado is False
    assert resultado.status == StatusElegibilidade.REJEITADO
    assert len(fake_notifier.eventos_falha) == 1
    assert fake_notifier.eventos_falha[0].atendimento_id == atend.id

    async with get_session_factory()() as session:
        refreshed = await session.get(Atendimento, atend.id)
        assert refreshed is not None
        assert (
            refreshed.status == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
        )

    async for valkey in get_valkey_client():
        score = await valkey.zscore("fila:aptos", str(atend.id))  # pyright: ignore[reportUnknownMemberType]
        assert score is None
