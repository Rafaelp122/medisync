"""Integration tests for PostgreSQL Row-Level Security (RLS) and DCL.

Adheres to ADR-003 and ADR-007.
"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import date
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from src.core.audit.models import AtorPapel, AtorTipo, AuditEvent
from src.core.context import tenant_context
from src.core.database import async_session_factory, engine
from src.core.uuid7 import uuid7
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    DocumentoItem,
    EvolucaoClinica,
    TipoDocumentoClinico,
)
from src.modules.identity.domain.models import (
    Dependente,
    Organizacao,
    Paciente,
    Profissional,
)
from src.modules.queue.domain.models import Atendimento
from src.modules.triage.domain.models import Triagem

if TYPE_CHECKING:
    from uuid import UUID

_MULTI_TENANT_TABLES = (
    "profissionais",
    "pacientes",
    "dependentes",
    "atendimentos",
    "triagens",
    "evolucoes_clinicas",
    "documentos_clinicos",
    "documento_itens",
    "audit_events",
)

_SAMPLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _run_alembic_upgrade_head() -> None:
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(autouse=True)
async def setup_rls_test_environment() -> AsyncGenerator[None, None]:
    """Ensure clean public schema and full migration up to head before each test."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DROP SCHEMA public CASCADE;
                CREATE SCHEMA public;
                GRANT ALL ON SCHEMA public TO medisync;
                GRANT ALL ON SCHEMA public TO public;
                CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
                CREATE EXTENSION IF NOT EXISTS "pgcrypto";
                """
            )
        )
    await asyncio.to_thread(_run_alembic_upgrade_head)
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DROP SCHEMA public CASCADE;
                CREATE SCHEMA public;
                GRANT ALL ON SCHEMA public TO medisync;
                GRANT ALL ON SCHEMA public TO public;
                CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
                CREATE EXTENSION IF NOT EXISTS "pgcrypto";
                """
            )
        )
    await asyncio.to_thread(_run_alembic_upgrade_head)


@pytest.mark.asyncio
async def test_rls_flags_and_policies_on_all_tables() -> None:
    """Verify that RLS is enabled and forced on all 9 tables and not on organizacoes."""
    async with engine.connect() as conn:
        res_rls = await conn.execute(
            text(
                """
                SELECT relname, relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE relname IN (
                    'profissionais', 'pacientes', 'dependentes', 'atendimentos',
                    'triagens', 'evolucoes_clinicas', 'documentos_clinicos',
                    'documento_itens', 'audit_events', 'organizacoes'
                )
                ORDER BY relname;
                """
            )
        )
        flags = {row[0]: (row[1], row[2]) for row in res_rls.fetchall()}

        for table in _MULTI_TENANT_TABLES:
            assert flags[table] == (True, True), (
                f"Table {table} must have rowsecurity=True and forcerowsecurity=True"
            )

        assert flags["organizacoes"] == (False, False)

        res_policies = await conn.execute(
            text(
                """
                SELECT tablename, policyname
                FROM pg_policies
                WHERE schemaname = 'public'
                ORDER BY tablename;
                """
            )
        )
        policies = {row[0]: row[1] for row in res_policies.fetchall()}
        for table in _MULTI_TENANT_TABLES:
            assert table in policies
            assert policies[table].startswith(f"tenant_isolation_{table}")


@pytest.mark.asyncio
async def test_tenant_isolation_across_all_nine_tables() -> None:
    """Verify strict tenant isolation across all 9 multi-tenant domain tables."""
    # 1. Setup base organizations without tenant context (admin / superuser)
    async with async_session_factory() as session:
        org1 = Organizacao(
            id=1001,
            cnpj="10010001000101",
            razao_social="Prefeitura Municipal Alfa",
            nome_fantasia="Saúde Alfa",
        )
        org2 = Organizacao(
            id=1002,
            cnpj="10020002000202",
            razao_social="Prefeitura Municipal Beta",
            nome_fantasia="Saúde Beta",
        )
        session.add_all([org1, org2])
        await session.commit()

    # 2. Insert complete aggregate records for Tenant 1
    prof1_id: UUID = uuid7()
    pac1_id: UUID = uuid7()
    dep1_id: UUID = uuid7()
    atend1_id: UUID = uuid7()
    doc1_id: UUID = uuid7()

    with tenant_context(1001):
        async with async_session_factory() as session:
            prof1 = Profissional(
                id=prof1_id,
                organizacao_id=1001,
                cpf="11111111111",
                nome_completo="Dr. Medico Alfa",
                email="medico@alfa.gov.br",
                papel="MEDICO",
                crm="11111",
                crm_uf="SP",
            )
            pac1 = Paciente(
                id=pac1_id,
                organizacao_id=1001,
                cpf="11111111112",
                data_nascimento=date(1990, 1, 1),
                telefone="11911111111",
                nome_completo="Paciente Titular Alfa",
            )
            dep_pac1 = Paciente(
                id=dep1_id,
                organizacao_id=1001,
                cpf="11111111113",
                data_nascimento=date(2015, 5, 20),
                telefone="11911111111",
                nome_completo="Paciente Dependente Alfa",
            )
            session.add_all([prof1, pac1, dep_pac1])
            await session.commit()

            dep1 = Dependente(
                organizacao_id=1001,
                titular_id=pac1_id,
                dependente_id=dep1_id,
                grau_parentesco="FILHO",
            )
            atend1 = Atendimento(
                id=atend1_id,
                organizacao_id=1001,
                paciente_id=pac1_id,
            )
            session.add_all([dep1, atend1])
            await session.commit()

            triagem1 = Triagem(
                organizacao_id=1001,
                atendimento_id=atend1_id,
                queixa_principal="Cefaleia moderada",
                prioridade_calculada=3,
            )
            evolucao1 = EvolucaoClinica(
                organizacao_id=1001,
                atendimento_id=atend1_id,
                medico_id=prof1_id,
                anamnese="Quadro estavel",
                conduta="Repouso",
            )
            doc1 = DocumentoClinico(
                id=doc1_id,
                organizacao_id=1001,
                atendimento_id=atend1_id,
                medico_id=prof1_id,
                tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
                chave_s3="alfa/rec1.pdf",
                sha256_hash=_SAMPLE_HASH,
            )
            session.add_all([triagem1, evolucao1, doc1])
            await session.commit()

            item1 = DocumentoItem(
                organizacao_id=1001,
                documento_id=doc1_id,
                medicamento="Dipirona 500mg",
                dosagem="1 cp",
                posologia="6/6h se dor",
            )
            audit1 = AuditEvent(
                organizacao_id=1001,
                atendimento_id=atend1_id,
                ator_tipo=AtorTipo.PROFISSIONAL,
                ator_id=prof1_id,
                ator_papel=AtorPapel.MEDICO,
                tipo_evento="CONSULTA_INICIADA",
            )
            session.add_all([item1, audit1])
            await session.commit()

    # 3. Insert complete aggregate records for Tenant 2
    prof2_id: UUID = uuid7()
    pac2_id: UUID = uuid7()
    dep2_id: UUID = uuid7()
    atend2_id: UUID = uuid7()
    doc2_id: UUID = uuid7()

    with tenant_context(1002):
        async with async_session_factory() as session:
            prof2 = Profissional(
                id=prof2_id,
                organizacao_id=1002,
                cpf="22222222221",
                nome_completo="Dra. Medica Beta",
                email="medica@beta.gov.br",
                papel="MEDICO",
                crm="22222",
                crm_uf="RJ",
            )
            pac2 = Paciente(
                id=pac2_id,
                organizacao_id=1002,
                cpf="22222222222",
                data_nascimento=date(1992, 2, 2),
                telefone="21922222222",
                nome_completo="Paciente Titular Beta",
            )
            dep_pac2 = Paciente(
                id=dep2_id,
                organizacao_id=1002,
                cpf="22222222223",
                data_nascimento=date(2018, 8, 15),
                telefone="21922222222",
                nome_completo="Paciente Dependente Beta",
            )
            session.add_all([prof2, pac2, dep_pac2])
            await session.commit()

            dep2 = Dependente(
                organizacao_id=1002,
                titular_id=pac2_id,
                dependente_id=dep2_id,
                grau_parentesco="FILHO",
            )
            atend2 = Atendimento(
                id=atend2_id,
                organizacao_id=1002,
                paciente_id=pac2_id,
            )
            session.add_all([dep2, atend2])
            await session.commit()

            triagem2 = Triagem(
                organizacao_id=1002,
                atendimento_id=atend2_id,
                queixa_principal="Febre baixa",
                prioridade_calculada=4,
            )
            evolucao2 = EvolucaoClinica(
                organizacao_id=1002,
                atendimento_id=atend2_id,
                medico_id=prof2_id,
                anamnese="Quadro gripal",
                conduta="Hidratacao",
            )
            doc2 = DocumentoClinico(
                id=doc2_id,
                organizacao_id=1002,
                atendimento_id=atend2_id,
                medico_id=prof2_id,
                tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
                chave_s3="beta/rec2.pdf",
                sha256_hash=_SAMPLE_HASH,
            )
            session.add_all([triagem2, evolucao2, doc2])
            await session.commit()

            item2 = DocumentoItem(
                organizacao_id=1002,
                documento_id=doc2_id,
                medicamento="Paracetamol 750mg",
                dosagem="1 cp",
                posologia="8/8h",
            )
            audit2 = AuditEvent(
                organizacao_id=1002,
                atendimento_id=atend2_id,
                ator_tipo=AtorTipo.PROFISSIONAL,
                ator_id=prof2_id,
                ator_papel=AtorPapel.MEDICO,
                tipo_evento="CONSULTA_INICIADA",
            )
            session.add_all([item2, audit2])
            await session.commit()

    # 4. Verify queries under Tenant 1 return ONLY Tenant 1 data
    with tenant_context(1001):
        async with async_session_factory() as session:
            profs = (await session.execute(select(Profissional))).scalars().all()
            assert len(profs) == 1
            assert profs[0].organizacao_id == 1001
            assert profs[0].id == prof1_id

            pacs = (await session.execute(select(Paciente))).scalars().all()
            assert len(pacs) == 2
            assert all(p.organizacao_id == 1001 for p in pacs)

            deps = (await session.execute(select(Dependente))).scalars().all()
            assert len(deps) == 1
            assert deps[0].organizacao_id == 1001

            atends = (await session.execute(select(Atendimento))).scalars().all()
            assert len(atends) == 1
            assert atends[0].organizacao_id == 1001
            assert atends[0].id == atend1_id

            triagens = (await session.execute(select(Triagem))).scalars().all()
            assert len(triagens) == 1
            assert triagens[0].organizacao_id == 1001

            evolucoes = (await session.execute(select(EvolucaoClinica))).scalars().all()
            assert len(evolucoes) == 1
            assert evolucoes[0].organizacao_id == 1001

            docs = (await session.execute(select(DocumentoClinico))).scalars().all()
            assert len(docs) == 1
            assert docs[0].organizacao_id == 1001
            assert docs[0].id == doc1_id

            items = (await session.execute(select(DocumentoItem))).scalars().all()
            assert len(items) == 1
            assert items[0].organizacao_id == 1001

            audits = (await session.execute(select(AuditEvent))).scalars().all()
            assert len(audits) == 1
            assert audits[0].organizacao_id == 1001

    # 5. Verify queries under Tenant 2 return ONLY Tenant 2 data
    with tenant_context(1002):
        async with async_session_factory() as session:
            profs = (await session.execute(select(Profissional))).scalars().all()
            assert len(profs) == 1
            assert profs[0].organizacao_id == 1002
            assert profs[0].id == prof2_id

            pacs = (await session.execute(select(Paciente))).scalars().all()
            assert len(pacs) == 2
            assert all(p.organizacao_id == 1002 for p in pacs)

            deps = (await session.execute(select(Dependente))).scalars().all()
            assert len(deps) == 1
            assert deps[0].organizacao_id == 1002

            atends = (await session.execute(select(Atendimento))).scalars().all()
            assert len(atends) == 1
            assert atends[0].organizacao_id == 1002
            assert atends[0].id == atend2_id

            triagens = (await session.execute(select(Triagem))).scalars().all()
            assert len(triagens) == 1
            assert triagens[0].organizacao_id == 1002

            evolucoes = (await session.execute(select(EvolucaoClinica))).scalars().all()
            assert len(evolucoes) == 1
            assert evolucoes[0].organizacao_id == 1002

            docs = (await session.execute(select(DocumentoClinico))).scalars().all()
            assert len(docs) == 1
            assert docs[0].organizacao_id == 1002
            assert docs[0].id == doc2_id

            items = (await session.execute(select(DocumentoItem))).scalars().all()
            assert len(items) == 1
            assert items[0].organizacao_id == 1002

            audits = (await session.execute(select(AuditEvent))).scalars().all()
            assert len(audits) == 1
            assert audits[0].organizacao_id == 1002


@pytest.mark.asyncio
async def test_rls_with_check_blocks_cross_tenant_insert() -> None:
    """Verify that WITH CHECK policy blocks inserting a record for another tenant."""
    # Setup base organizations
    async with async_session_factory() as session:
        org1 = Organizacao(
            id=2001,
            cnpj="20010001000101",
            razao_social="Org 2001",
            nome_fantasia="O1",
        )
        org2 = Organizacao(
            id=2002,
            cnpj="20020002000202",
            razao_social="Org 2002",
            nome_fantasia="O2",
        )
        session.add_all([org1, org2])
        await session.commit()

    with tenant_context(2001):
        async with async_session_factory() as session:
            # Attempt to insert a Paciente belonging to org 2002 while under tenant 2001
            paciente_mismatch = Paciente(
                organizacao_id=2002,
                cpf="99988877766",
                data_nascimento=date(1980, 10, 10),
                telefone="11999887766",
                nome_completo="Intruder Paciente",
            )
            session.add(paciente_mismatch)
            with pytest.raises(DBAPIError) as exc_info:
                await session.commit()

            assert "row-level security policy" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_fail_safe_deny_without_tenant() -> None:
    """Verify that queries executed as medisync_app without tenant return 0 rows."""
    async with async_session_factory() as session:
        org = Organizacao(
            id=3001,
            cnpj="30010001000101",
            razao_social="Org 3001",
            nome_fantasia="O3",
        )
        session.add(org)
        await session.commit()

    with tenant_context(3001):
        async with async_session_factory() as session:
            pac = Paciente(
                organizacao_id=3001,
                cpf="33333333333",
                data_nascimento=date(1995, 3, 3),
                telefone="11933333333",
                nome_completo="Paciente Test Deny",
            )
            session.add(pac)
            await session.commit()

    # Query directly using medisync_app with empty tenant
    async with engine.connect() as conn, conn.begin():
        await conn.execute(text("SET LOCAL ROLE medisync_app;"))
        await conn.execute(
            text("SELECT set_config('app.current_tenant_id', '', true);")
        )
        result = await conn.execute(text("SELECT * FROM pacientes;"))
        rows = result.fetchall()
        assert rows == []


@pytest.mark.asyncio
async def test_audit_events_dcl_and_trigger_security() -> None:
    """Verify medisync_app can INSERT into audit_events but cannot UPDATE/DELETE."""
    event_id: UUID = uuid7()
    atend_id: UUID = uuid7()

    async with engine.connect() as conn:
        async with conn.begin():
            # Setup prerequisite records without RLS
            await conn.execute(
                text(
                    """
                    INSERT INTO organizacoes (id, cnpj, razao_social, nome_fantasia)
                    VALUES (4001, '40010001000101', 'Org 4001', 'O4');
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO pacientes (
                        id, organizacao_id, cpf, data_nascimento, telefone
                    )
                    VALUES (
                        '01a00000-0000-7000-8000-000000000041', 4001,
                        '44444444444', '1990-01-01', '11944444444'
                    );
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO atendimentos (id, organizacao_id, paciente_id, status)
                    VALUES (
                        :atend_id, 4001, '01a00000-0000-7000-8000-000000000041',
                        'TRIADO_AGUARDANDO_ELEGIBILIDADE'
                    );
                    """
                ),
                {"atend_id": atend_id},
            )

        # 1. INSERT as medisync_app with tenant 4001: must succeed
        async with conn.begin():
            await conn.execute(text("SET LOCAL ROLE medisync_app;"))
            await conn.execute(
                text("SELECT set_config('app.current_tenant_id', '4001', true);")
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO audit_events (
                        id, organizacao_id, atendimento_id, ator_tipo,
                        ator_papel, tipo_evento, registrado_em
                    )
                    VALUES (
                        :id, 4001, :atend_id, 'SISTEMA',
                        'SISTEMA', 'DCL_TEST_EVENT', NOW() AT TIME ZONE 'UTC'
                    );
                    """
                ),
                {"id": event_id, "atend_id": atend_id},
            )

        # 2. UPDATE as medisync_app: must fail
        async with conn.begin():
            await conn.execute(text("SET LOCAL ROLE medisync_app;"))
            await conn.execute(
                text("SELECT set_config('app.current_tenant_id', '4001', true);")
            )
            with pytest.raises(DBAPIError) as exc_info:
                await conn.execute(
                    text(
                        """
                        UPDATE audit_events
                        SET tipo_evento = 'TAMPERED'
                        WHERE id = :id;
                        """
                    ),
                    {"id": event_id},
                )
            error_msg = str(exc_info.value).lower()
            assert "permission denied" in error_msg or "append-only" in error_msg

        # 3. DELETE as medisync_app: must fail
        async with conn.begin():
            await conn.execute(text("SET LOCAL ROLE medisync_app;"))
            await conn.execute(
                text("SELECT set_config('app.current_tenant_id', '4001', true);")
            )
            with pytest.raises(DBAPIError) as exc_info:
                await conn.execute(
                    text("DELETE FROM audit_events WHERE id = :id;"),
                    {"id": event_id},
                )
            error_msg = str(exc_info.value).lower()
            assert "permission denied" in error_msg or "append-only" in error_msg
