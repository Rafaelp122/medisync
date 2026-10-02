"""Integration tests for asynchronous Alembic migrations pipeline with Psycopg 3."""

import asyncio
from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from src.core.database import engine

_EXPECTED_TABLES = frozenset(
    [
        "alembic_version",
        "organizacoes",
        "profissionais",
        "pacientes",
        "dependentes",
        "atendimentos",
        "triagens",
        "evolucoes_clinicas",
        "documentos_clinicos",
        "documento_itens",
        "audit_events",
    ]
)


def _run_alembic_upgrade_head() -> None:
    """Execute alembic upgrade head synchronously in a dedicated thread."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


def _run_alembic_downgrade_base() -> None:
    """Execute alembic downgrade base synchronously in a dedicated thread."""
    alembic_cfg = Config("alembic.ini")
    command.downgrade(alembic_cfg, "base")


@pytest.fixture(autouse=True)
async def ensure_clean_migration_state() -> AsyncGenerator[None, None]:
    """Reset public schema completely and run upgrade head before each test."""
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


@pytest.mark.asyncio
async def test_migration_creates_all_ten_clinical_tables() -> None:
    """Verify that alembic upgrade head creates all expected domain tables."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
                """
            )
        )
        existing_tables = {row[0] for row in result.fetchall()}

    assert _EXPECTED_TABLES.issubset(existing_tables)


@pytest.mark.asyncio
async def test_gen_uuidv7_creates_valid_rfc9562_uuid() -> None:
    """Verify that PostgreSQL gen_uuidv7() generates RFC 9562 UUIDv7 values."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT gen_uuidv7();"))
        generated_uuid_str = result.scalar()

    assert generated_uuid_str is not None
    parsed_uuid = UUID(str(generated_uuid_str))
    assert parsed_uuid.version == 7


@pytest.mark.asyncio
async def test_partial_unique_indexes_on_pacientes() -> None:
    """Verify partial unique indexes uq_paciente_org_cpf and uq_paciente_org_cns."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'pacientes'
                ORDER BY indexname;
                """
            )
        )
        indexes = {row[0]: row[1] for row in result.fetchall()}

    assert "uq_paciente_org_cpf" in indexes
    assert "WHERE (cpf IS NOT NULL)" in indexes["uq_paciente_org_cpf"]

    assert "uq_paciente_org_cns" in indexes
    assert "WHERE (cns IS NOT NULL)" in indexes["uq_paciente_org_cns"]


@pytest.mark.asyncio
async def test_check_constraints_registered() -> None:
    """Verify critical check constraints on clinical aggregate tables."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE constraint_type = 'CHECK'
                  AND table_schema = 'public'
                ORDER BY constraint_name;
                """
            )
        )
        constraints = {row[0] for row in result.fetchall()}

    expected_checks = {
        "chk_documento_paciente_obrigatorio",
        "chk_atendimento_status",
        "chk_atendimento_prioridade",
        "chk_triagem_prioridade",
        "chk_documentos_tipo",
        "chk_documentos_sha256_len",
        "chk_audit_ator_tipo",
    }
    assert expected_checks.issubset(constraints)


@pytest.mark.asyncio
async def test_audit_immutable_trigger_blocks_mutations() -> None:
    """Verify ADR-007 anti-tampering trigger blocks UPDATE on audit_events."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO organizacoes (id, cnpj, razao_social, nome_fantasia)
                VALUES (88881, '88881111000188', 'Org Test Migration', 'Org Mig')
                ON CONFLICT DO NOTHING;

                INSERT INTO pacientes (
                    id, organizacao_id, cpf, data_nascimento, telefone
                )
                VALUES (
                    '01a00000-0000-7000-8000-000000000011',
                    88881,
                    '88881111888',
                    '1985-05-15',
                    '11988881111'
                )
                ON CONFLICT DO NOTHING;

                INSERT INTO atendimentos (id, organizacao_id, paciente_id, status)
                VALUES (
                    '01a00000-0000-7000-8000-000000000012',
                    88881,
                    '01a00000-0000-7000-8000-000000000011',
                    'TRIADO_AGUARDANDO_ELEGIBILIDADE'
                )
                ON CONFLICT DO NOTHING;

                INSERT INTO audit_events (
                    id, organizacao_id, atendimento_id, ator_tipo,
                    ator_papel, tipo_evento
                )
                VALUES (
                    '01a00000-0000-7000-8000-000000000013',
                    88881,
                    '01a00000-0000-7000-8000-000000000012',
                    'SISTEMA',
                    'SISTEMA',
                    'MIGRATION_AUDIT_CHECK'
                );
                """
            )
        )

        with pytest.raises(DBAPIError) as exc_info:
            await conn.execute(
                text(
                    """
                    UPDATE audit_events
                    SET tipo_evento = 'TAMPERED'
                    WHERE id = '01a00000-0000-7000-8000-000000000013';
                    """
                )
            )

        assert "append-only" in str(exc_info.value)


@pytest.mark.asyncio
async def test_downgrade_base_and_reupgrade_lifecycle() -> None:
    """Verify complete rollback to base and subsequent upgrade to head."""
    # Downgrade to base
    await asyncio.to_thread(_run_alembic_downgrade_base)

    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name != 'alembic_version';
                """
            )
        )
        remaining_tables = [row[0] for row in result.fetchall()]

    assert remaining_tables == []

    # Re-upgrade to head
    await asyncio.to_thread(_run_alembic_upgrade_head)

    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
                """
            )
        )
        recreated_tables = {row[0] for row in result.fetchall()}

    assert _EXPECTED_TABLES.issubset(recreated_tables)
