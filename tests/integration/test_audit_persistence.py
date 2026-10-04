"""Integration tests for AuditEvent persistence and PostgreSQL triggers (ADR-007)."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from src.core.audit.models import AtorPapel, AtorTipo, AuditEvent
from src.core.audit.service import AuditService
from src.core.database import Base, async_session_factory, engine
from src.modules.queue.domain.models import Atendimento

from tests.factories.audit import make_audit_event
from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento

_SAMPLE_TCLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.fixture(autouse=True)
async def setup_audit_tables() -> AsyncGenerator[None, None]:
    """Create all domain tables, indexes, and ADR-007 immutable trigger."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # ADR-007: Trigger restritiva para garantir imutabilidade física no PostgreSQL
        await conn.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION trg_prevent_audit_mutation()
                RETURNS TRIGGER AS $$
                BEGIN
                    RAISE EXCEPTION 'A tabela audit_events é estritamente append-only '
                        '(CFM 2.314/2022 e LGPD Art. 11). Operações de UPDATE ou '
                        'DELETE são terminantemente proibidas.'
                        USING ERRCODE = 'restrict_violation';
                END;
                $$ LANGUAGE plpgsql;

                DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit_events;
                CREATE TRIGGER trg_audit_events_immutable
                BEFORE UPDATE OR DELETE ON audit_events
                FOR EACH ROW EXECUTE FUNCTION trg_prevent_audit_mutation();
                """
            )
        )
    yield
    from tests.helpers import clean_database_tables

    await clean_database_tables()


@pytest.mark.asyncio
async def test_persist_audit_event_success() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="10101010000101")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="10101010101")
        medico = make_profissional(
            org.id,
            cpf="20202020202",
            email="dr.audit@ubs.gov.br",
            papel="MEDICO",
            crm="99881",
            crm_uf="SP",
        )
        session.add_all([paciente, medico])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico)

        atendimento = make_atendimento(org.id, paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        org_id = org.id
        atend_id = atendimento.id
        medico_id = medico.id

        evt = await AuditService.record_event(
            session,
            organizacao_id=org_id,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.PROFISSIONAL,
            ator_papel=AtorPapel.MEDICO,
            tipo_evento="CHAMADA_INICIADA",
            ator_id=medico_id,
            estado_anterior="APTO_PARA_CHAMADA",
            novo_estado="CHAMANDO_PACIENTE",
            tcle_hash=_SAMPLE_TCLE_HASH,
            payload={"canal": "WEBRTC", "sala": "sala_101"},
            ip_origem="192.168.0.50",
        )
        await session.commit()

        evt_id = evt.id

        # Query de volta
        stmt = select(AuditEvent).where(AuditEvent.id == evt_id)
        res = await session.execute(stmt)
        evt_recuperado = res.scalar_one()

        assert evt_recuperado.id == evt_id
        assert evt_recuperado.organizacao_id == org_id
        assert evt_recuperado.atendimento_id == atend_id
        assert evt_recuperado.ator_tipo == AtorTipo.PROFISSIONAL
        assert evt_recuperado.ator_id == medico_id
        assert evt_recuperado.tcle_hash == _SAMPLE_TCLE_HASH
        assert evt_recuperado.payload == {"canal": "WEBRTC", "sala": "sala_101"}
        assert str(evt_recuperado.ip_origem).startswith("192.168.0.50")
        assert evt_recuperado.registrado_em is not None


@pytest.mark.asyncio
async def test_database_trigger_blocks_update_and_delete() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="20202020000102")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="30303030303")
        medico = make_profissional(
            org.id,
            cpf="40404040404",
            email="dr.sec@ubs.gov.br",
            papel="MEDICO",
            crm="88772",
            crm_uf="RJ",
        )
        session.add_all([paciente, medico])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico)

        atendimento = make_atendimento(org.id, paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        org_id = org.id
        atend_id = atendimento.id
        medico_id = medico.id

        evt = make_audit_event(
            organizacao_id=org_id,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.PROFISSIONAL,
            ator_papel=AtorPapel.MEDICO,
            tipo_evento="TRIAGEM_INICIADA",
            ator_id=medico_id,
        )
        session.add(evt)
        await session.commit()

        evt_id = evt.id

        # 1. Tentar UPDATE direto no PostgreSQL deve acionar a trigger restritiva
        sql_update = text(
            "UPDATE audit_events SET tipo_evento = 'MUTADO' WHERE id = :id"
        )
        with pytest.raises(DBAPIError) as exc_info:
            await session.execute(sql_update, {"id": evt_id})
            await session.commit()
        await session.rollback()
        assert "append-only" in str(exc_info.value).lower()

        # 2. Tentar DELETE direto no PostgreSQL deve acionar a trigger restritiva
        sql_delete = text("DELETE FROM audit_events WHERE id = :id")
        with pytest.raises(DBAPIError) as exc_info_del:
            await session.execute(sql_delete, {"id": evt_id})
            await session.commit()
        await session.rollback()
        assert "append-only" in str(exc_info_del.value).lower()


@pytest.mark.asyncio
async def test_on_delete_restrict_atendimento_with_audit_events() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="30303030000103")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="50505050505")
        medico = make_profissional(
            org.id,
            cpf="60606060606",
            email="dr.restr@ubs.gov.br",
            papel="MEDICO",
            crm="77663",
            crm_uf="MG",
        )
        session.add_all([paciente, medico])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico)

        atendimento = make_atendimento(org.id, paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        org_id = org.id
        atend_id = atendimento.id
        medico_id = medico.id

        evt = make_audit_event(
            organizacao_id=org_id,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.PROFISSIONAL,
            ator_papel=AtorPapel.MEDICO,
            tipo_evento="ELEGIBILIDADE_CONFIRMADA",
            ator_id=medico_id,
        )
        session.add(evt)
        await session.commit()

        # Tentar deletar o atendimento deve violar ON DELETE RESTRICT
        atend_obj = await session.get(Atendimento, atend_id)
        assert atend_obj is not None
        await session.delete(atend_obj)

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_audit_service_list_events_chronological_order() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="40404040000104")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="70707070707")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(org.id, paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        org_id = org.id
        atend_id = atendimento.id
        base_time = datetime.now(UTC)

        # Inserir eventos com tempos sequenciais
        evt1 = make_audit_event(
            organizacao_id=org_id,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.SISTEMA,
            ator_papel=AtorPapel.SISTEMA,
            tipo_evento="PASSO_1",
            registrado_em=base_time - timedelta(minutes=5),
        )
        evt2 = make_audit_event(
            organizacao_id=org_id,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.SISTEMA,
            ator_papel=AtorPapel.SISTEMA,
            tipo_evento="PASSO_2",
            registrado_em=base_time - timedelta(minutes=2),
        )
        evt3 = make_audit_event(
            organizacao_id=org_id,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.SISTEMA,
            ator_papel=AtorPapel.SISTEMA,
            tipo_evento="PASSO_3",
            registrado_em=base_time,
        )
        session.add_all([evt2, evt1, evt3])  # Adicionados fora de ordem
        await session.commit()

        # Listar eventos através do AuditService
        eventos = await AuditService.list_events_by_atendimento(session, atend_id)
        assert len(eventos) == 3
        assert [e.tipo_evento for e in eventos] == ["PASSO_1", "PASSO_2", "PASSO_3"]


@pytest.mark.asyncio
async def test_database_check_constraint_ator_tipo() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="50505050000105")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="80808080808")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(org.id, paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        org_id = org.id
        atend_id = atendimento.id

        sql_invalid_ator = text(
            "INSERT INTO audit_events ("
            "id, organizacao_id, atendimento_id, ator_tipo, ator_papel, "
            "tipo_evento, registrado_em"
            ") VALUES ("
            ":id, :org_id, :atend_id, 'ROBOT_INVALIDO', 'SISTEMA', "
            "'TESTE', NOW()"
            ")"
        )
        with pytest.raises(IntegrityError):
            await session.execute(
                sql_invalid_ator,
                {
                    "id": uuid4(),
                    "org_id": org_id,
                    "atend_id": atend_id,
                },
            )
            await session.commit()
        await session.rollback()
