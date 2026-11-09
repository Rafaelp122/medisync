"""Unit tests for the 180s antifraud duration floor for certificates
(CFM 2.314/2022).
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest
from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.core.errors import TravaAntiFraudeAtestadoError
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoResumoDTO,
)
from src.modules.consultation.application.services.documento_service import (
    DocumentoService,
)
from src.modules.consultation.domain.models import (
    TipoDocumentoClinico,
)
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)

from tests.doubles import (
    FakeAddedResult,
    FakeAsyncSession,
    FakeAtendimentoReader,
    FakeAuditTrail,
    FakeICPBrasilSigner,
    FakeMemoryStorage,
    FakePDFGenerator,
    FakeResult,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _make_resumo_com_inicio(
    atendimento_id: UUID, segundos_atras: int
) -> AtendimentoResumoDTO:
    now = datetime.now(UTC)
    inicio = now - timedelta(seconds=segundos_atras)
    return AtendimentoResumoDTO(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=uuid4(),
        status="EM_ATENDIMENTO",
        tcle_hash="b" * 64,
        is_terminal=False,
        chamada_iniciada_em=inicio,
        criado_em=inicio,
    )


def _build_service(
    session: FakeAsyncSession,
    reader: FakeAtendimentoReader,
    audit_trail: AuditTrailPort | None = None,
) -> DocumentoService:
    return DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=FakeMemoryStorage(),
        cache=MemorySignedCache(),
        atendimento_reader=reader,
        audit_trail=audit_trail,
    )


@pytest.mark.asyncio
async def test_emissao_atestado_inferior_180s_sem_justificativa_bloqueada() -> None:
    atendimento_id = uuid4()
    medico_id = uuid4()
    reader = FakeAtendimentoReader(
        resumo=_make_resumo_com_inicio(atendimento_id, segundos_atras=35)
    )
    fake_audit = FakeAuditTrail()

    session = FakeAsyncSession(results=[FakeResult(None)])
    svc = _build_service(session, reader, audit_trail=fake_audit)

    cmd = EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.ATESTADO_MEDICO,
        justificativa_tempo_inferior=None,
    )

    with pytest.raises(TravaAntiFraudeAtestadoError) as exc_info:
        await svc.emitir_documento(cmd)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "TRAVA_TEMPORAL_ATESTADO_VIOLADA"
    assert "inferior ao piso de 180s" in str(exc_info.value)
    assert "mínimo de 15 caracteres" in str(exc_info.value)

    events = fake_audit.get_events_by_type("TRAVA_TEMPORAL_ATESTADO_VIOLADA")
    assert len(events) == 1
    evt = events[0]
    assert evt["organizacao_id"] == 1
    assert evt["atendimento_id"] == atendimento_id
    assert evt["ator_tipo"] == AtorTipo.PROFISSIONAL.value
    assert evt["ator_papel"] == AtorPapel.MEDICO.value
    assert evt["ator_id"] == medico_id
    assert evt["payload"]["justificativa_aceita"] is False
    assert evt["payload"]["justificativa"] == ""
    assert evt["payload"]["duracao_segundos"] >= 0.0


@pytest.mark.asyncio
async def test_emissao_atestado_inferior_180s_com_justificativa_curta_bloqueada() -> (
    None
):
    atendimento_id = uuid4()
    medico_id = uuid4()
    reader = FakeAtendimentoReader(
        resumo=_make_resumo_com_inicio(atendimento_id, segundos_atras=50)
    )
    fake_audit = FakeAuditTrail()

    session = FakeAsyncSession(results=[FakeResult(None)])
    svc = _build_service(session, reader, audit_trail=fake_audit)

    cmd = EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.ATESTADO_MEDICO,
        justificativa_tempo_inferior="urgente rápido",  # 14 chars
    )

    with pytest.raises(TravaAntiFraudeAtestadoError) as exc_info:
        await svc.emitir_documento(cmd)

    assert exc_info.value.status_code == 422
    assert "urgente rápido" in str(exc_info.value)

    events = fake_audit.get_events_by_type("TRAVA_TEMPORAL_ATESTADO_VIOLADA")
    assert len(events) == 1
    evt = events[0]
    assert evt["payload"]["justificativa_aceita"] is False
    assert evt["payload"]["justificativa"] == "urgente rápido"


@pytest.mark.asyncio
async def test_emissao_atestado_inferior_180s_com_justificativa_valida_permitida() -> (
    None
):
    atendimento_id = uuid4()
    medico_id = uuid4()
    reader = FakeAtendimentoReader(
        resumo=_make_resumo_com_inicio(atendimento_id, segundos_atras=60)
    )
    fake_audit = FakeAuditTrail()

    added_entities: list[object] = []
    session = FakeAsyncSession(
        [
            FakeResult(None),  # evolucao select
            FakeAddedResult(added_entities),  # reload after commit
        ],
        added_entities,
    )
    svc = _build_service(session, reader, audit_trail=fake_audit)

    justificativa = (
        "Atendimento complementar referente a retorno imediato pós-exame presencial."
    )
    cmd = EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.ATESTADO_MEDICO,
        justificativa_tempo_inferior=justificativa,
    )

    doc = await svc.emitir_documento(cmd)

    assert doc.tipo_documento == TipoDocumentoClinico.ATESTADO_MEDICO
    assert doc.justificativa_tempo_inferior == justificativa

    events = fake_audit.get_events_by_type("TRAVA_TEMPORAL_ATESTADO_VIOLADA")
    assert len(events) == 1
    evt = events[0]
    assert evt["organizacao_id"] == 1
    assert evt["atendimento_id"] == atendimento_id
    assert evt["ator_tipo"] == AtorTipo.PROFISSIONAL.value
    assert evt["ator_papel"] == AtorPapel.MEDICO.value
    assert evt["ator_id"] == medico_id
    assert evt["payload"]["justificativa_aceita"] is True
    assert evt["payload"]["justificativa"] == justificativa
    assert evt["payload"]["duracao_segundos"] >= 0.0


@pytest.mark.asyncio
async def test_emissao_atestado_superior_180s_sem_justificativa_permitida() -> None:
    atendimento_id = uuid4()
    medico_id = uuid4()
    reader = FakeAtendimentoReader(
        resumo=_make_resumo_com_inicio(atendimento_id, segundos_atras=250)
    )
    fake_audit = FakeAuditTrail()

    added_entities: list[object] = []
    session = FakeAsyncSession(
        [
            FakeResult(None),  # evolucao select
            FakeAddedResult(added_entities),  # reload after commit
        ],
        added_entities,
    )
    svc = _build_service(session, reader, audit_trail=fake_audit)

    cmd = EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.ATESTADO_MEDICO,
        justificativa_tempo_inferior=None,
    )

    doc = await svc.emitir_documento(cmd)

    assert doc.tipo_documento == TipoDocumentoClinico.ATESTADO_MEDICO
    assert doc.justificativa_tempo_inferior is None
    assert len(fake_audit.get_events_by_type("TRAVA_TEMPORAL_ATESTADO_VIOLADA")) == 0


@pytest.mark.asyncio
async def test_emissao_receita_inferior_180s_nao_aciona_trava() -> None:
    atendimento_id = uuid4()
    medico_id = uuid4()
    reader = FakeAtendimentoReader(
        resumo=_make_resumo_com_inicio(atendimento_id, segundos_atras=20)
    )
    fake_audit = FakeAuditTrail()

    added_entities: list[object] = []
    session = FakeAsyncSession(
        [
            FakeResult(None),  # evolucao select
            FakeAddedResult(added_entities),  # reload after commit
        ],
        added_entities,
    )
    svc = _build_service(session, reader, audit_trail=fake_audit)

    cmd = EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        organizacao_id=1,
        medico_id=medico_id,
        tipo_documento="RECEITA_SIMPLES",
        itens=[
            CriarItemPrescricaoDTO(
                medicamento="Paracetamol",
                dosagem="750mg",
                posologia="1 cp 6/6h se dor",
            )
        ],
        justificativa_tempo_inferior=None,
    )

    doc = await svc.emitir_documento(cmd)

    assert doc.tipo_documento == TipoDocumentoClinico.RECEITA_SIMPLES
    assert len(fake_audit.get_events_by_type("TRAVA_TEMPORAL_ATESTADO_VIOLADA")) == 0
