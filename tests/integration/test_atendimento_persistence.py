"""Integration tests for Atendimento persistence and constraints in PostgreSQL 17."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from src.core.database import async_session_factory
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento
from tests.helpers import clean_database_tables

SAMPLE_TCLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.fixture(autouse=True)
async def setup_atendimento_tables() -> AsyncGenerator[None, None]:
    """Clean tables before each test and after."""
    await clean_database_tables()
    yield
    await clean_database_tables()


@pytest.mark.asyncio
async def test_persist_atendimento_lifecycle_happy_path() -> None:
    async with async_session_factory() as session:
        # 1. Setup base relational entities
        org = make_organizacao(cnpj="12345678000199")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="11122233344")
        medico = make_profissional(
            org.id,
            cpf="99988877766",
            email="dr.carlos@ubs.gov.br",
            papel="MEDICO",
            crm="123456",
            crm_uf="SP",
        )
        session.add_all([paciente, medico])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico)

        # 2. Insert Atendimento in initial triage state
        atendimento = make_atendimento(
            organizacao_id=org.id,
            paciente_id=paciente.id,
            prioridade_clinica=PrioridadeClinica.URGENTE,
            tcle_hash=SAMPLE_TCLE_HASH,
        )
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        assert atendimento.id is not None
        assert atendimento.status == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE
        assert atendimento.tcle_hash == SAMPLE_TCLE_HASH

        # 3. Promote to APTO_PARA_CHAMADA
        atendimento.promover_para_apto()
        await session.commit()
        await session.refresh(atendimento)
        assert atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA
        assert atendimento.data_entrada_fila is not None

        # 4. Initiate call by doctor
        atendimento.iniciar_chamada(medico_id=medico.id)
        await session.commit()
        await session.refresh(atendimento)
        assert atendimento.status == StatusAtendimento.CHAMANDO_PACIENTE
        assert atendimento.medico_id == medico.id
        assert atendimento.chamada_iniciada_em is not None

        # 5. Answer call
        atendimento.atender_chamada()
        await session.commit()
        await session.refresh(atendimento)
        assert atendimento.status == StatusAtendimento.EM_ATENDIMENTO

        # 6. Conclude attendance
        atendimento.concluir_atendimento()
        await session.commit()
        await session.refresh(atendimento)
        assert atendimento.status == StatusAtendimento.CONCLUIDO
        assert atendimento.chamada_finalizada_em is not None


@pytest.mark.asyncio
async def test_atendimento_foreign_key_violation_paciente() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="22334455000188")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        # Atendimento referencing nonexistent paciente_id
        non_existent_paciente_id = uuid4()
        atendimento = make_atendimento(
            organizacao_id=org.id,
            paciente_id=non_existent_paciente_id,
            tcle_hash=SAMPLE_TCLE_HASH,
        )
        session.add(atendimento)

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_atendimento_foreign_key_violation_organizacao() -> None:
    async with async_session_factory() as session:
        atendimento = make_atendimento(
            organizacao_id=999999,
            paciente_id=uuid4(),
            tcle_hash=SAMPLE_TCLE_HASH,
        )
        session.add(atendimento)

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_atendimento_chk_status_violation_raw_db() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="33445566000177")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="33344455566")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        insert_stmt = text(
            """
            INSERT INTO atendimentos (
                id, organizacao_id, paciente_id, status, prioridade_clinica,
                criado_em, atualizado_em
            ) VALUES (
                gen_random_uuid(), :org_id, :paciente_id, 'STATUS_INVALIDO', 3,
                NOW(), NOW()
            )
            """
        )

        with pytest.raises(IntegrityError, match="chk_atendimento_status"):
            await session.execute(
                insert_stmt, {"org_id": org.id, "paciente_id": paciente.id}
            )
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_atendimento_chk_prioridade_violation_raw_db() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="44556677000166")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="44455566677")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        insert_stmt = text(
            """
            INSERT INTO atendimentos (
                id, organizacao_id, paciente_id, status, prioridade_clinica,
                criado_em, atualizado_em
            ) VALUES (
                gen_random_uuid(), :org_id, :paciente_id,
                'TRIADO_AGUARDANDO_ELEGIBILIDADE', 6, NOW(), NOW()
            )
            """
        )

        with pytest.raises(IntegrityError, match="chk_atendimento_prioridade"):
            await session.execute(
                insert_stmt, {"org_id": org.id, "paciente_id": paciente.id}
            )
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_atendimento_no_show_persistence() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="55667788000155")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="55566677788")
        medico = make_profissional(
            org.id,
            cpf="88877766655",
            email="dr.plantao@ubs.gov.br",
            papel="MEDICO",
        )
        session.add_all([paciente, medico])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico)

        atendimento = make_atendimento(
            organizacao_id=org.id,
            paciente_id=paciente.id,
            tcle_hash=SAMPLE_TCLE_HASH,
        )
        atendimento.promover_para_apto()
        atendimento.iniciar_chamada(medico_id=medico.id)
        session.add(atendimento)
        await session.commit()

        atendimento.registrar_ausencia_paciente()
        await session.commit()
        await session.refresh(atendimento)

        assert atendimento.status == StatusAtendimento.PACIENTE_AUSENTE
        assert atendimento.chamada_finalizada_em is not None


@pytest.mark.asyncio
async def test_atendimento_cancelamento_paciente_persistence() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="66778899000144")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="66677788899")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(
            organizacao_id=org.id,
            paciente_id=paciente.id,
            tcle_hash=SAMPLE_TCLE_HASH,
        )
        atendimento.cancelar_pelo_paciente(motivo="Demora na resposta")
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        assert atendimento.status == StatusAtendimento.CANCELADO_PACIENTE
        assert atendimento.is_finalizado is True


@pytest.mark.asyncio
async def test_atendimento_query_by_fila_composite_index() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="77889900000133")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        p1 = make_paciente(org.id, cpf="77711122233")
        p2 = make_paciente(org.id, cpf="77722233344")
        p3 = make_paciente(org.id, cpf="77733344455")
        session.add_all([p1, p2, p3])
        await session.commit()
        await session.refresh(p1)
        await session.refresh(p2)
        await session.refresh(p3)

        now = datetime.now(UTC)

        a1 = make_atendimento(
            org.id,
            p1.id,
            prioridade_clinica=PrioridadeClinica.POUCO_URGENTE,
            tcle_hash=SAMPLE_TCLE_HASH,
            status=StatusAtendimento.APTO_PARA_CHAMADA,
            data_entrada_fila=now - timedelta(minutes=10),
        )
        a2 = make_atendimento(
            org.id,
            p2.id,
            prioridade_clinica=PrioridadeClinica.MUITO_URGENTE,
            tcle_hash=SAMPLE_TCLE_HASH,
            status=StatusAtendimento.APTO_PARA_CHAMADA,
            data_entrada_fila=now - timedelta(minutes=2),
        )
        a3 = make_atendimento(
            org.id,
            p3.id,
            prioridade_clinica=PrioridadeClinica.MUITO_URGENTE,
            tcle_hash=SAMPLE_TCLE_HASH,
            status=StatusAtendimento.APTO_PARA_CHAMADA,
            data_entrada_fila=now - timedelta(minutes=5),
        )

        session.add_all([a1, a2, a3])
        await session.commit()

        # Query ordering by priority ASC, then FIFO data_entrada_fila ASC (RN01)
        query = (
            select(Atendimento)
            .where(
                Atendimento.organizacao_id == org.id,
                Atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA.value,
            )
            .order_by(
                Atendimento.prioridade_clinica.asc(),
                Atendimento.data_entrada_fila.asc(),
            )
        )
        result = await session.execute(query)
        ordenados = list(result.scalars().all())

        assert [a.id for a in ordenados] == [a3.id, a2.id, a1.id]
