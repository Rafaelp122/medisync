"""Integration tests for identity persistence, constraints, and relationships."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories.identity import (
    make_dependente,
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.scenarios import seed_multi_tenant_orgs

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_persist_organizacao_and_profissional(db_session: AsyncSession) -> None:
    """Validate basic persistence and relationship of organizacao and profissional."""
    org = make_organizacao(cnpj="98765432000199", razao_social="Prefeitura Municipal")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

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
    db_session.add(prof)
    await db_session.commit()
    await db_session.refresh(prof)

    assert prof.id is not None
    assert prof.papel == "MEDICO"
    assert prof.crm == "998877"


@pytest.mark.asyncio
async def test_profissional_unique_email_per_org_violation(
    db_session: AsyncSession,
) -> None:
    """Validate email uniqueness is strictly scoped per organization."""
    org_a, org_b = await seed_multi_tenant_orgs(
        db_session, cnpj_a="11223344000155", cnpj_b="11223344000156"
    )

    # Same email in distinct organizations is allowed
    p1 = make_profissional(org_a.id, email="compartilhado@org.com", cpf="11111111111")
    p_other = make_profissional(
        org_b.id, email="compartilhado@org.com", cpf="33333333333"
    )
    db_session.add_all([p1, p_other])
    await db_session.commit()

    # Same email within the same organization triggers IntegrityError
    p2 = make_profissional(org_a.id, email="compartilhado@org.com", cpf="22222222222")
    db_session.add(p2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_paciente_pediatrico_persisted_without_cpf(
    db_session: AsyncSession,
) -> None:
    """Validate pediatric patient can be persisted with CNS when CPF is absent."""
    org = make_organizacao(cnpj="33445566000177")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    recem_nascido = make_paciente(
        org.id,
        cpf=None,
        cns="898000123456789",
        data_nascimento=date.today(),
        nome_completo="Recém Nascido de Maria",
    )
    db_session.add(recem_nascido)
    await db_session.commit()
    await db_session.refresh(recem_nascido)

    assert recem_nascido.id is not None
    assert recem_nascido.cpf is None
    assert recem_nascido.cns == "898000123456789"


@pytest.mark.asyncio
async def test_paciente_partial_unique_index_allows_multiple_null_cpfs(
    db_session: AsyncSession,
) -> None:
    """Validate partial unique index allows multiple NULL CPFs under the same tenant."""
    org = make_organizacao(cnpj="44556677000188")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

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
    db_session.add_all([bebe1, bebe2])
    await db_session.commit()
    await db_session.refresh(bebe1)
    await db_session.refresh(bebe2)

    assert bebe1.id != bebe2.id
    assert bebe1.cpf is None
    assert bebe2.cpf is None


@pytest.mark.asyncio
async def test_paciente_duplicate_cpf_raises_integrity_error(
    db_session: AsyncSession,
) -> None:
    """Validate identical CPFs within the same organization violate uniqueness."""
    org = make_organizacao(cnpj="77889900000122")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    pac1 = make_paciente(org.id, cpf="99988877766", cns="333000123456789")
    db_session.add(pac1)
    await db_session.commit()

    pac2 = make_paciente(org.id, cpf="99988877766", cns="444000123456789")
    db_session.add(pac2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_dependente_linkage_persisted(db_session: AsyncSession) -> None:
    """Validate titular and dependent patient linkage persistence."""
    org = make_organizacao(cnpj="55667788000188")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    titular = make_paciente(org.id, cpf="77788899900", nome_completo="Mãe Titular")
    filho = make_paciente(
        org.id, cpf=None, cns="777000111222333", nome_completo="Filho Dependente"
    )
    db_session.add_all([titular, filho])
    await db_session.commit()
    await db_session.refresh(titular)
    await db_session.refresh(filho)

    dep = make_dependente(
        org.id,
        titular_id=titular.id,
        dependente_id=filho.id,
        grau_parentesco="FILHO",
    )
    db_session.add(dep)
    await db_session.commit()
    await db_session.refresh(dep)

    assert dep.id is not None
    assert dep.titular_id == titular.id
    assert dep.dependente_id == filho.id


@pytest.mark.asyncio
async def test_dependente_duplicate_linkage_raises_integrity_error(
    db_session: AsyncSession,
) -> None:
    """Validate duplicate titular-dependent pairs violate uniqueness."""
    org = make_organizacao(cnpj="66778899000199")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    titular = make_paciente(org.id, cpf="88899900011", nome_completo="Pai Titular")
    filho = make_paciente(
        org.id, cpf=None, cns="888000111222333", nome_completo="Filho Único"
    )
    db_session.add_all([titular, filho])
    await db_session.commit()
    await db_session.refresh(titular)
    await db_session.refresh(filho)

    d1 = make_dependente(org.id, titular_id=titular.id, dependente_id=filho.id)
    db_session.add(d1)
    await db_session.commit()

    d2 = make_dependente(org.id, titular_id=titular.id, dependente_id=filho.id)
    db_session.add(d2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
