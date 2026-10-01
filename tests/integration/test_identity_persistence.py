from collections.abc import AsyncGenerator
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from src.core.database import Base, async_session_factory, engine

from tests.factories.identity import (
    make_dependente,
    make_organizacao,
    make_paciente,
    make_profissional,
)


@pytest.fixture(autouse=True)
async def setup_identity_tables() -> AsyncGenerator[None, None]:
    """Create tables in PostgreSQL before testing and drop on cleanup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_persist_organizacao_and_profissional() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(
            cnpj="98765432000199", razao_social="Prefeitura Municipal"
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)

        assert org.id is not None
        assert org.id > 0

        prof = make_profissional(
            organizacao_id=org.id,
            email="plantao@prefeitura.gov.br",
            cpf="12345678909",
            nome_completo="Dr. Carlos Plantonista",
            papel="MEDICO",
            crm="998877",
            crm_uf="SP",
        )
        session.add(prof)
        await session.commit()
        await session.refresh(prof)

        assert prof.id is not None
        assert prof.papel == "MEDICO"
        assert prof.crm == "998877"


@pytest.mark.asyncio
async def test_profissional_unique_email_per_org_violation() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="11223344000155")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        p1 = make_profissional(org.id, email="duplicado@org.com", cpf="11111111111")
        session.add(p1)
        await session.commit()

        p2 = make_profissional(org.id, email="duplicado@org.com", cpf="22222222222")
        session.add(p2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_paciente_pediatrico_persisted_without_cpf() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="33445566000177")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        recem_nascido = make_paciente(
            org.id,
            cpf=None,
            cns="898000123456789",
            data_nascimento=date.today(),
            nome_completo="Recém Nascido de Maria",
        )
        session.add(recem_nascido)
        await session.commit()
        await session.refresh(recem_nascido)

        assert recem_nascido.id is not None
        assert recem_nascido.cpf is None
        assert recem_nascido.cns == "898000123456789"


@pytest.mark.asyncio
async def test_paciente_partial_unique_index_allows_multiple_null_cpfs() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="44556677000188")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        bebe1 = make_paciente(
            org.id,
            cpf=None,
            cns="111000123456789",
            data_nascimento=date.today(),
            nome_completo="Bebê Um",
        )
        bebe2 = make_paciente(
            org.id,
            cpf=None,
            cns="222000123456789",
            data_nascimento=date.today(),
            nome_completo="Bebê Dois",
        )
        session.add_all([bebe1, bebe2])
        await session.commit()
        await session.refresh(bebe1)
        await session.refresh(bebe2)

        assert bebe1.id != bebe2.id
        assert bebe1.cpf is None
        assert bebe2.cpf is None


@pytest.mark.asyncio
async def test_paciente_duplicate_cpf_raises_integrity_error() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="77889900000122")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        pac1 = make_paciente(org.id, cpf="99988877766", cns="333000123456789")
        session.add(pac1)
        await session.commit()

        pac2 = make_paciente(org.id, cpf="99988877766", cns="444000123456789")
        session.add(pac2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_dependente_linkage_persisted() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="55667788000188")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        titular = make_paciente(org.id, cpf="77788899900", nome_completo="Mãe Titular")
        filho = make_paciente(
            org.id, cpf=None, cns="777000111222333", nome_completo="Filho Dependente"
        )
        session.add_all([titular, filho])
        await session.commit()
        await session.refresh(titular)
        await session.refresh(filho)

        dep = make_dependente(
            org.id,
            titular_id=titular.id,
            dependente_id=filho.id,
            grau_parentesco="FILHO",
        )
        session.add(dep)
        await session.commit()
        await session.refresh(dep)

        assert dep.id is not None
        assert dep.titular_id == titular.id
        assert dep.dependente_id == filho.id


@pytest.mark.asyncio
async def test_dependente_duplicate_linkage_raises_integrity_error() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="66778899000199")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        titular = make_paciente(org.id, cpf="88899900011", nome_completo="Pai Titular")
        filho = make_paciente(
            org.id, cpf=None, cns="888000111222333", nome_completo="Filho Único"
        )
        session.add_all([titular, filho])
        await session.commit()
        await session.refresh(titular)
        await session.refresh(filho)

        d1 = make_dependente(org.id, titular_id=titular.id, dependente_id=filho.id)
        session.add(d1)
        await session.commit()

        d2 = make_dependente(org.id, titular_id=titular.id, dependente_id=filho.id)
        session.add(d2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
