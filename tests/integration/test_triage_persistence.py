"""Integration tests for Triagem persistence and constraints in PostgreSQL 17."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from src.core.database import get_session_factory

from tests.factories.identity import make_paciente
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
    async with get_session_factory()() as session:
        paciente = make_paciente(cpf="11122233301")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        triagem = make_triagem(
            atendimento_id=atendimento.id,
            queixa_principal="Cefaleia moderada com náuseas",
            prioridade_calculada=3,
            escala_dor=5,
            sintomas_alerta=["cefaleia", "nauseas"],
        )
        session.add(triagem)
        await session.commit()
        await session.refresh(triagem)

        assert triagem.id is not None
        assert triagem.atendimento_id == atendimento.id
        assert triagem.prioridade_calculada == 3
        assert triagem.sintomas_alerta == ["cefaleia", "nauseas"]
        assert triagem.alerta_samu_disparado is False


@pytest.mark.asyncio
async def test_triagem_foreign_key_violation_atendimento() -> None:
    async with get_session_factory()() as session:
        non_existent_atendimento_id = uuid4()
        triagem = make_triagem(atendimento_id=non_existent_atendimento_id)
        session.add(triagem)

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_triagem_unique_1_to_1_per_atendimento() -> None:
    async with get_session_factory()() as session:
        paciente = make_paciente(cpf="22233344402")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        t1 = make_triagem(atendimento.id, queixa_principal="Primeira")
        session.add(t1)
        await session.commit()

        # Segunda triagem apontando para o mesmo atendimento_id viola 1:1 único
        t2 = make_triagem(atendimento.id, queixa_principal="Segunda")
        session.add(t2)

        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_triagem_chk_prioridade_violation_raw_db() -> None:
    async with get_session_factory()() as session:
        paciente = make_paciente(cpf="33344455503")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        insert_stmt = text(
            """
            INSERT INTO triagens (
                id, atendimento_id, queixa_principal,
                sintomas_alerta, alerta_samu_disparado, prioridade_calculada,
                avaliado_em
            ) VALUES (
                gen_random_uuid(), :atendimento_id, 'Dor',
                '[]'::jsonb, FALSE, 6, NOW()
            )
            """
        )

        with pytest.raises(IntegrityError, match="chk_triagem_prioridade"):
            await session.execute(insert_stmt, {"atendimento_id": atendimento.id})
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_triagem_emergency_samu_persistence() -> None:
    async with get_session_factory()() as session:
        paciente = make_paciente(cpf="44455566604")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atendimento = make_atendimento(paciente.id)
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

        triagem = make_triagem(
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
