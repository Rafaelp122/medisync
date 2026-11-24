"""AtendimentoReaderPort returns DTO, None when missing, maps terminal statuses."""

import logging
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
from src.modules.consultation.infrastructure.atendimento_reader_sql import (
    SqlAtendimentoReader,
)

from tests.doubles import FakeAsyncSession, FakeResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_reader_mapeia_terminal() -> None:
    session = FakeAsyncSession(
        results=[
            FakeResult(
                mappings_rows=[
                    {
                        "id": uuid4(),
                        "medico_id": uuid4(),
                        "status": "CONCLUIDO",
                        "tcle_hash": "a" * 64,
                    }
                ]
            )
        ]
    )
    reader = SqlAtendimentoReader(cast("AsyncSession", session))
    dto = await reader.obter_resumo(uuid4())
    assert dto is not None and dto.is_terminal is True


@pytest.mark.asyncio
async def test_reader_nao_terminal_e_none_quando_ausente() -> None:
    atend_id = uuid4()
    medico_id = uuid4()
    session = FakeAsyncSession(
        results=[
            FakeResult(
                mappings_rows=[
                    {
                        "id": atend_id,
                        "medico_id": medico_id,
                        "status": "EM_ATENDIMENTO",
                        "tcle_hash": None,
                    }
                ]
            ),
            FakeResult(mappings_rows=[]),
        ]
    )
    reader = SqlAtendimentoReader(cast("AsyncSession", session))

    dto = await reader.obter_resumo(atend_id)
    assert dto is not None
    assert dto.is_terminal is False
    assert dto.status == "EM_ATENDIMENTO"
    assert dto.medico_id == medico_id

    assert await reader.obter_resumo(uuid4()) is None


@pytest.mark.asyncio
async def test_reader_concluir_atendimento_executes_and_commits() -> None:
    session = FakeAsyncSession()
    reader = SqlAtendimentoReader(cast("AsyncSession", session))
    atend_id = uuid4()
    await reader.concluir_atendimento(atend_id)
    assert session.executes == 1
    assert session.commits == 1


@pytest.mark.asyncio
async def test_reader_atender_chamada_executes_and_commits() -> None:
    session = FakeAsyncSession()
    reader = SqlAtendimentoReader(cast("AsyncSession", session))
    atend_id = uuid4()
    await reader.atender_chamada(atend_id)
    assert session.executes == 1
    assert session.commits == 1


def test_get_atendimento_reader_fallback_logs_warning(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.modules.consultation import composition as cons_comp

    def _failing_builder(*args: object, **kwargs: object) -> object:
        raise RuntimeError("queue_init_failed")

    monkeypatch.setattr(cons_comp, "build_fila_service_for_session", _failing_builder)
    session = FakeAsyncSession()
    with caplog.at_level(logging.WARNING):
        reader = cons_comp.get_atendimento_reader(cast("AsyncSession", session))
        assert isinstance(reader, SqlAtendimentoReader)
        assert "Falha ao instanciar QueueStoreAtendimentoReaderAdapter" in caplog.text
