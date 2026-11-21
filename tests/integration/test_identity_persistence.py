"""Integration tests for identity persistence, constraints, and relationships."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories.identity import (
    make_configuracao_unidade,
    make_dependente,
    make_paciente,
    make_profissional,
)

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_persist_configuracao_unidade_singleton_and_profissional(
    db_session: AsyncSession,
) -> None:
    """Validate singleton persistence of configuracoes_unidade and profissional."""
    unidade = make_configuracao_unidade(
        cnpj="98765432000199", razao_social="Prefeitura Municipal"
    )
    db_session.add(unidade)
    await db_session.commit()
    await db_session.refresh(unidade)

    assert unidade.id is not None

    # Singleton guard must block second unit config row
    duplicada = make_configuracao_unidade(
        cnpj="11223344000100", razao_social="Segunda Unidade Proibida"
    )
    db_session.add(duplicada)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    prof = make_profissional(
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
async def test_profissional_unique_email_global_violation(
    db_session: AsyncSession,
) -> None:
    """Validate email uniqueness is globally enforced across the platform."""
    p1 = make_profissional(email="plantao.unico@org.com", cpf="11111111111")
    p_other = make_profissional(email="outro.email@org.com", cpf="33333333333")
    db_session.add_all([p1, p_other])
    await db_session.commit()

    p2 = make_profissional(email="plantao.unico@org.com", cpf="22222222222")
    db_session.add(p2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_paciente_pediatrico_persisted_without_cpf(
    db_session: AsyncSession,
) -> None:
    """Validate pediatric patient can be persisted with CNS when CPF is absent."""
    recem_nascido = make_paciente(
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
    """Validate partial unique index allows multiple NULL CPFs globally."""
    bebe1 = make_paciente(
        cpf=None,
        cns="111000123456789",
        data_nascimento=date.today(),
        nome_completo="Bebê Um",
        telefone="11987654321",
    )
    bebe2 = make_paciente(
        cpf=None,
        cns="222000123456789",
        data_nascimento=date.today(),
        nome_completo="Bebê Dois",
        telefone="11987654322",
    )
    db_session.add_all([bebe1, bebe2])
    await db_session.commit()
    await db_session.refresh(bebe1)
    await db_session.refresh(bebe2)

    assert bebe1.id != bebe2.id
    assert bebe1.cpf is None


@pytest.mark.asyncio
async def test_paciente_duplicate_cpf_raises_integrity_error(
    db_session: AsyncSession,
) -> None:
    """Validate identical CPFs violate global uniqueness."""
    pac1 = make_paciente(cpf="99988877766", cns="333000123456789")
    db_session.add(pac1)
    await db_session.commit()

    pac2 = make_paciente(
        cpf="99988877766", cns="444000123456789", telefone="11987654399"
    )
    db_session.add(pac2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_dependente_linkage_persisted(db_session: AsyncSession) -> None:
    """Validate titular and dependent patient linkage persistence."""
    titular = make_paciente(
        cpf="77788899900", nome_completo="Mãe Titular", telefone="11911112222"
    )
    filho = make_paciente(
        cpf=None,
        cns="777000111222333",
        nome_completo="Filho Dependente",
        telefone="11911113333",
    )
    db_session.add_all([titular, filho])
    await db_session.commit()
    await db_session.refresh(titular)
    await db_session.refresh(filho)

    dep = make_dependente(
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
    titular = make_paciente(
        cpf="88899900011", nome_completo="Pai Titular", telefone="11944445555"
    )
    filho = make_paciente(
        cpf=None,
        cns="888000111222333",
        nome_completo="Filho Único",
        telefone="11944446666",
    )
    db_session.add_all([titular, filho])
    await db_session.commit()
    await db_session.refresh(titular)
    await db_session.refresh(filho)

    d1 = make_dependente(titular_id=titular.id, dependente_id=filho.id)
    db_session.add(d1)
    await db_session.commit()

    d2 = make_dependente(titular_id=titular.id, dependente_id=filho.id)
    db_session.add(d2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
