"""Integration tests for consultation PEP persistence and constraints in Postgres 17."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from src.core.database import Base, async_session_factory, engine
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
from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento


@pytest.fixture(autouse=True)
async def setup_consultation_tables() -> AsyncGenerator[None, None]:
    """Create all domain tables before testing and drop on cleanup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_persist_evolucao_clinica_success() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="11111111000101")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="11111111101")
        medico = make_profissional(
            org.id,
            cpf="22222222201",
            email="dra.ana@ubs.gov.br",
            papel="MEDICO",
            crm="12345",
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

        evolucao = make_evolucao_clinica(
            organizacao_id=org_id,
            atendimento_id=atend_id,
            medico_id=medico_id,
            anamnese="Paciente com coriza, febre baixa e mialgia há 36h.",
            exame_fisico_virtual="Bom estado geral, sem esforço respiratório.",
            cid10_principal="J06.9",
            conduta="Prescrito paracetamol e lavagem nasal com soro fisiológico.",
        )
        session.add(evolucao)
        await session.commit()
        await session.refresh(evolucao)

        assert evolucao.id is not None
        assert evolucao.organizacao_id == org_id
        assert evolucao.atendimento_id == atend_id
        assert evolucao.medico_id == medico_id
        assert evolucao.cid10_principal == "J06.9"
        assert evolucao.registrado_em is not None


@pytest.mark.asyncio
async def test_persist_documento_clinico_e_itens_rls_compliance() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="22222222000102")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="33333333302")
        medico = make_profissional(
            org.id,
            cpf="44444444402",
            email="dr.pedro@ubs.gov.br",
            papel="MEDICO",
            crm="54321",
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
        session.add(doc_simples)
        await session.commit()

        doc_simples_id = doc_simples.id

        # 2. Query com selectinload e verificação de organizacao_id explícito (RLS)
        stmt = (
            select(DocumentoClinico)
            .where(DocumentoClinico.id == doc_simples_id)
            .options(selectinload(DocumentoClinico.itens))
        )
        res = await session.execute(stmt)
        doc_recuperado = res.scalar_one()

        assert len(doc_recuperado.itens) == 2
        for it in doc_recuperado.itens:
            assert it.organizacao_id == org_id  # Essencial para PostgreSQL RLS
            assert it.documento_id == doc_simples_id
            assert it.controle_especial is False


@pytest.mark.asyncio
async def test_cascade_delete_documento_itens_on_documento_delete() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="33333333000103")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="55555555503")
        medico = make_profissional(
            org.id,
            cpf="66666666603",
            email="dr.marcos@ubs.gov.br",
            papel="MEDICO",
            crm="67890",
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
        session.add(doc)
        await session.commit()

        doc_id = doc.id

        # Deletar o documento
        await session.delete(doc)
        await session.commit()

        # Verificar que o item foi deletado em cascata
        stmt_itens = select(DocumentoItem).where(DocumentoItem.documento_id == doc_id)
        res_itens = await session.execute(stmt_itens)
        itens_restantes = res_itens.scalars().all()
        assert len(itens_restantes) == 0


@pytest.mark.asyncio
async def test_on_delete_restrict_atendimento_with_evolucoes_and_documentos() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="44444444000104")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="77777777704")
        medico = make_profissional(
            org.id,
            cpf="88888888804",
            email="dra.juliana@ubs.gov.br",
            papel="MEDICO",
            crm="98765",
            crm_uf="RS",
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

        evolucao = make_evolucao_clinica(
            organizacao_id=org_id,
            atendimento_id=atend_id,
            medico_id=medico_id,
        )
        session.add(evolucao)
        await session.commit()

        evolucao_id = evolucao.id

        # Tentar excluir atendimento deve falhar por ON DELETE RESTRICT
        atend_para_excluir = await session.get(Atendimento, atend_id)
        assert atend_para_excluir is not None
        await session.delete(atend_para_excluir)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        # Excluir evolução primeiro, depois criar documento
        evolucao_db = await session.get(EvolucaoClinica, evolucao_id)
        assert evolucao_db is not None
        await session.delete(evolucao_db)
        await session.commit()

        doc = make_documento_clinico(
            organizacao_id=org_id,
            atendimento_id=atend_id,
            medico_id=medico_id,
        )
        session.add(doc)
        await session.commit()

        # Tentar excluir atendimento deve falhar novamente pelo documento
        atend_para_excluir2 = await session.get(Atendimento, atend_id)
        assert atend_para_excluir2 is not None
        await session.delete(atend_para_excluir2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_database_check_constraints_documentos() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="55555555000105")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="99999999905")
        medico = make_profissional(
            org.id,
            cpf="00011122205",
            email="dr.bruno@ubs.gov.br",
            papel="MEDICO",
            crm="11223",
            crm_uf="SC",
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
            await session.execute(
                sql_invalid_tipo,
                {
                    "id": uuid4(),
                    "org_id": org_id,
                    "atend_id": atend_id,
                    "med_id": medico_id,
                    "hash": "a" * 64,
                },
            )
            await session.commit()
        await session.rollback()

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
            await session.execute(
                sql_invalid_hash,
                {
                    "id": uuid4(),
                    "org_id": org_id,
                    "atend_id": atend_id,
                    "med_id": medico_id,
                },
            )
            await session.commit()
        await session.rollback()
