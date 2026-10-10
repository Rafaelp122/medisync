"""Integration tests for consultation PEP persistence and constraints in Postgres 17."""

from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    DocumentoItem,
    EvolucaoClinica,
    TipoDocumentoClinico,
)
from src.modules.queue.domain.models import Atendimento

from tests.factories.consultation import (
    make_documento_clinico,
    make_documento_item,
    make_evolucao_clinica,
)
from tests.factories.scenarios import seed_clinical_scenario

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_persist_evolucao_clinica_success(db_session: AsyncSession) -> None:
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="11111111000101",
        paciente_cpf="11111111101",
        medico_cpf="22222222201",
    )
    org_id = cenario.organizacao.id
    atend_id = cenario.atendimento.id
    medico_id = cenario.medico.id

    evolucao = make_evolucao_clinica(
        organizacao_id=org_id,
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com coriza, febre baixa e mialgia há 36h.",
        exame_fisico_virtual="Bom estado geral, sem esforço respiratório.",
        cid10_principal="J06.9",
        conduta="Prescrito paracetamol e lavagem nasal com soro fisiológico.",
    )
    db_session.add(evolucao)
    await db_session.commit()
    await db_session.refresh(evolucao)

    assert evolucao.id is not None
    assert evolucao.organizacao_id == org_id
    assert evolucao.atendimento_id == atend_id
    assert evolucao.medico_id == medico_id
    assert evolucao.cid10_principal == "J06.9"
    assert evolucao.registrado_em is not None


@pytest.mark.asyncio
async def test_persist_documento_clinico_e_itens_rls_compliance(
    db_session: AsyncSession,
) -> None:
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="22222222000102",
        paciente_cpf="33333333302",
        medico_cpf="44444444402",
    )
    org_id = cenario.organizacao.id
    atend_id = cenario.atendimento.id
    medico_id = cenario.medico.id

    # 1. Documento simples com itens
    doc_simples = make_documento_clinico(
        organizacao_id=org_id,
        atendimento_id=atend_id,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="s3://medisync-docs/2/atendimentos/doc1.pdf",
    )
    item1 = make_documento_item(
        organizacao_id=org_id,
        documento_id=doc_simples.id,
        medicamento="Dipirona Monoidratada 500mg",
        dosagem="1 comp",
        posologia="Tomar 1 comp 6/6h se dor ou febre",
        duracao="3 dias",
    )
    item2 = make_documento_item(
        organizacao_id=org_id,
        documento_id=doc_simples.id,
        medicamento="Paracetamol 750mg",
        dosagem="1 comp",
        posologia="Tomar 1 comp 8/8h se dor",
        duracao="5 dias",
    )
    doc_simples.adicionar_item(item1)
    doc_simples.adicionar_item(item2)
    db_session.add(doc_simples)
    await db_session.commit()

    doc_simples_id = doc_simples.id

    # 2. Query com selectinload e verificação de organizacao_id explícito (RLS)
    stmt = (
        select(DocumentoClinico)
        .where(DocumentoClinico.id == doc_simples_id)
        .options(selectinload(DocumentoClinico.itens))
    )
    res = await db_session.execute(stmt)
    doc_recuperado = res.scalar_one()

    assert len(doc_recuperado.itens) == 2
    for it in doc_recuperado.itens:
        assert it.organizacao_id == org_id  # Essencial para PostgreSQL RLS
        assert it.documento_id == doc_simples_id
        assert it.controle_especial is False


@pytest.mark.asyncio
async def test_cascade_delete_documento_itens_on_documento_delete(
    db_session: AsyncSession,
) -> None:
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="33333333000103",
        paciente_cpf="55555555503",
        medico_cpf="66666666603",
    )
    org_id = cenario.organizacao.id
    atend_id = cenario.atendimento.id
    medico_id = cenario.medico.id

    doc = make_documento_clinico(
        organizacao_id=org_id,
        atendimento_id=atend_id,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.RECEITA_ANTIMICROBIANO,
        chave_s3="s3://medisync-docs/3/atendimentos/doc_amox.pdf",
    )
    item = make_documento_item(
        organizacao_id=org_id,
        documento_id=doc.id,
        medicamento="Amoxicilina 500mg",
        dosagem="1 capsula",
        posologia="1 capsula de 8/8h por 7 dias",
        duracao="7 dias",
    )
    doc.adicionar_item(item)
    db_session.add(doc)
    await db_session.commit()

    doc_id = doc.id

    # Deletar o documento
    await db_session.delete(doc)
    await db_session.commit()

    # Verificar que o item foi deletado em cascata
    stmt_itens = select(DocumentoItem).where(DocumentoItem.documento_id == doc_id)
    res_itens = await db_session.execute(stmt_itens)
    itens_restantes = res_itens.scalars().all()
    assert len(itens_restantes) == 0


@pytest.mark.asyncio
async def test_on_delete_restrict_atendimento_with_evolucoes_and_documentos(
    db_session: AsyncSession,
) -> None:
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="44444444000104",
        paciente_cpf="77777777704",
        medico_cpf="88888888804",
    )
    org_id = cenario.organizacao.id
    atend_id = cenario.atendimento.id
    medico_id = cenario.medico.id

    evolucao = make_evolucao_clinica(
        organizacao_id=org_id,
        atendimento_id=atend_id,
        medico_id=medico_id,
    )
    db_session.add(evolucao)
    await db_session.commit()

    evolucao_id = evolucao.id

    # Tentar excluir atendimento deve falhar por ON DELETE RESTRICT
    atend_para_excluir = await db_session.get(Atendimento, atend_id)
    assert atend_para_excluir is not None
    await db_session.delete(atend_para_excluir)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # Excluir evolução primeiro, depois criar documento
    evolucao_db = await db_session.get(EvolucaoClinica, evolucao_id)
    assert evolucao_db is not None
    await db_session.delete(evolucao_db)
    await db_session.commit()

    doc = make_documento_clinico(
        organizacao_id=org_id,
        atendimento_id=atend_id,
        medico_id=medico_id,
    )
    db_session.add(doc)
    await db_session.commit()

    # Tentar excluir atendimento deve falhar novamente pelo documento
    atend_para_excluir2 = await db_session.get(Atendimento, atend_id)
    assert atend_para_excluir2 is not None
    await db_session.delete(atend_para_excluir2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_database_check_constraints_documentos(
    db_session: AsyncSession,
) -> None:
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="55555555000105",
        paciente_cpf="99999999905",
        medico_cpf="00011122205",
    )
    org_id = cenario.organizacao.id
    atend_id = cenario.atendimento.id
    medico_id = cenario.medico.id

    # 1. Violação de CheckConstraint tipo_documento no PostgreSQL
    sql_invalid_tipo = text(
        "INSERT INTO documentos_clinicos ("
        "id, organizacao_id, atendimento_id, medico_id, tipo_documento, "
        "chave_s3, sha256_hash, assinado_em"
        ") VALUES ("
        ":id, :org_id, :atend_id, :med_id, 'TIPO_INEXISTENTE', "
        "'s3://bucket/test.pdf', :hash, NOW()"
        ")"
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(
            sql_invalid_tipo,
            {
                "id": uuid4(),
                "org_id": org_id,
                "atend_id": atend_id,
                "med_id": medico_id,
                "hash": "a" * 64,
            },
        )
        await db_session.commit()
    await db_session.rollback()

    # 2. Violação de CheckConstraint sha256_hash length != 64
    sql_invalid_hash = text(
        "INSERT INTO documentos_clinicos ("
        "id, organizacao_id, atendimento_id, medico_id, tipo_documento, "
        "chave_s3, sha256_hash, assinado_em"
        ") VALUES ("
        ":id, :org_id, :atend_id, :med_id, 'RECEITA_SIMPLES', "
        "'s3://bucket/test.pdf', 'hash_curto', NOW()"
        ")"
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(
            sql_invalid_hash,
            {
                "id": uuid4(),
                "org_id": org_id,
                "atend_id": atend_id,
                "med_id": medico_id,
            },
        )
        await db_session.commit()
    await db_session.rollback()
