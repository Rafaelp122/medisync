"""Integration tests for Triagem persistence and constraints in PostgreSQL 17."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from src.core.database import async_session_factory

from tests.factories.identity import make_organizacao, make_paciente
from tests.factories.queue import make_atendimento
from tests.factories.triage import make_triagem
from tests.helpers import clean_database_tables


@pytest.fixture(autouse=True)
async def setup_triage_tables() -> AsyncGenerator[None, None]:
    """Clean tables before each test and after."""
    await clean_database_tables()
    yield
    await clean_database_tables()


@pytest.mark.asyncio
async def test_persist_triagem_success() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="12345678000101")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="11122233301")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(org.id, paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        triagem = make_triagem(
            organizacao_id=org.id,
            atendimento_id=atendimento.id,
            queixa_principal="Cefaleia moderada com náuseas",
            prioridade_calculada=3,
            sintomas_alerta=["cefaleia", "nauseas"],
        )
        session.add(triagem)
        await session.commit()
        await session.refresh(triagem)

        assert triagem.id is not None
        assert triagem.organizacao_id == org.id
        assert triagem.atendimento_id == atendimento.id
        assert triagem.prioridade_calculada == 3
        assert triagem.sintomas_alerta == ["cefaleia", "nauseas"]
        assert triagem.alerta_samu_disparado is False


@pytest.mark.asyncio
async def test_triagem_foreign_key_violation_atendimento() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="22334455000102")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        non_existent_atendimento_id = uuid4()
        triagem = make_triagem(
            organizacao_id=org.id,
            atendimento_id=non_existent_atendimento_id,
        )
        session.add(triagem)

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_triagem_unique_1_to_1_per_atendimento() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="33445566000103")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="22233344402")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(org.id, paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        t1 = make_triagem(org.id, atendimento.id, queixa_principal="Primeira")
        session.add(t1)
        await session.commit()

        # Segunda triagem apontando para o mesmo atendimento_id viola 1:1 único
        t2 = make_triagem(org.id, atendimento.id, queixa_principal="Segunda")
        session.add(t2)

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_triagem_chk_prioridade_violation_raw_db() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="44556677000104")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="33344455503")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(org.id, paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        insert_stmt = text(
            """
            INSERT INTO triagens (
                id, organizacao_id, atendimento_id, queixa_principal,
                sintomas_alerta, alerta_samu_disparado, prioridade_calculada,
                avaliado_em
            ) VALUES (
                gen_random_uuid(), :org_id, :atendimento_id, 'Dor',
                '[]'::jsonb, FALSE, 6, NOW()
            )
            """
        )

        with pytest.raises(IntegrityError, match="chk_triagem_prioridade"):
            await session.execute(
                insert_stmt,
                {"org_id": org.id, "atendimento_id": atendimento.id},
            )
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_triagem_emergency_samu_persistence() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="55667788000105")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="44455566604")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(org.id, paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        triagem = make_triagem(
            organizacao_id=org.id,
            atendimento_id=atendimento.id,
            queixa_principal="Dor torácica com irradiação aguda para MSE",
            prioridade_calculada=1,
            sintomas_alerta=["dor_toracica_irradiada", "diaforese"],
            alerta_samu_disparado=True,
        )
        session.add(triagem)
        await session.commit()
        await session.refresh(triagem)

        assert triagem.prioridade_calculada == 1
        assert triagem.alerta_samu_disparado is True
        assert "dor_toracica_irradiada" in triagem.sintomas_alerta
        assert triagem.is_emergencia_critica is True
