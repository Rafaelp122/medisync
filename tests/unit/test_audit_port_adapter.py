"""Unit tests for AuditTrailPort, SqlAuditTrailAdapter, and FakeAuditTrail (ADR-007).

Decisões: docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md
Referência: docs/reference/audit/event-catalog.md
"""

from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import (
    AtorPapel,
    AtorTipo,
    AuditEvent,
    AuditTrailPort,
    SqlAuditTrailAdapter,
)
from src.core.audit.ports import AuditTrailPort as DirectAuditTrailPort
from src.core.uuid7 import uuid7

from tests.doubles import FakeAsyncSession, FakeAuditTrail


@pytest.mark.asyncio
async def test_sql_audit_trail_adapter_satisfies_protocol() -> None:
    session = FakeAsyncSession()
    adapter: AuditTrailPort = SqlAuditTrailAdapter(cast("AsyncSession", session))
    assert isinstance(adapter, DirectAuditTrailPort)


@pytest.mark.asyncio
async def test_sql_audit_trail_adapter_records_event_in_session() -> None:
    session = FakeAsyncSession()
    adapter = SqlAuditTrailAdapter(cast("AsyncSession", session))

    org_id = 1
    atendimento_id = uuid7()
    medico_id = uuid7()

    event_id = await adapter.record_event(
        organizacao_id=org_id,
        atendimento_id=atendimento_id,
        ator_tipo=AtorTipo.PROFISSIONAL,
        ator_papel=AtorPapel.MEDICO,
        tipo_evento="CHAMADA_INICIADA",
        ator_id=medico_id,
        estado_anterior="APTO_PARA_CHAMADA",
        novo_estado="CHAMANDO_PACIENTE",
        payload={"ring_timeout_segundos": 45},
    )

    assert isinstance(event_id, UUID)
    assert len(session.added) == 1
    event = session.added[0]
    assert isinstance(event, AuditEvent)
    assert event.id == event_id
    assert event.organizacao_id == org_id
    assert event.atendimento_id == atendimento_id
    assert event.ator_tipo == AtorTipo.PROFISSIONAL
    assert event.ator_papel == AtorPapel.MEDICO
    assert event.ator_id == medico_id
    assert event.tipo_evento == "CHAMADA_INICIADA"
    assert event.estado_anterior == "APTO_PARA_CHAMADA"
    assert event.novo_estado == "CHAMANDO_PACIENTE"
    assert event.payload == {"ring_timeout_segundos": 45}


@pytest.mark.asyncio
async def test_fake_audit_trail_satisfies_protocol_and_records_in_memory() -> None:
    fake: AuditTrailPort = FakeAuditTrail()

    org_id = 2
    atendimento_id = uuid7()
    paciente_id = uuid7()

    event_id = await fake.record_event(
        organizacao_id=org_id,
        atendimento_id=atendimento_id,
        ator_tipo="PACIENTE",
        ator_papel="PACIENTE",
        tipo_evento="ADMISSAO_PACIENTE",
        ator_id=paciente_id,
        estado_anterior=None,
        novo_estado="TRIADO_AGUARDANDO_ELEGIBILIDADE",
        tcle_hash="a" * 64,
        payload={"prioridade_clinica": 2},
    )

    assert isinstance(event_id, UUID)
    assert len(fake.events) == 1
    record = fake.events[0]
    assert record["id"] == event_id
    assert record["tipo_evento"] == "ADMISSAO_PACIENTE"
    assert record["tcle_hash"] == "a" * 64

    filtered = fake.get_events_by_type("ADMISSAO_PACIENTE")
    assert len(filtered) == 1

    fake.clear()
    assert len(fake.events) == 0
