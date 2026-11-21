"""Integration tests for asynchronous Alembic migrations pipeline with Psycopg 3."""

import asyncio
from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from src.core.database import get_engine

_EXPECTED_TABLES = frozenset(
    [
        "alembic_version",
        "configuracoes_unidade",
        "profissionais",
        "pacientes",
        "dependentes",
        "atendimentos",
        "triagens",
        "evolucoes_clinicas",
        "documentos_clinicos",
        "documento_itens",
        "audit_events",
        "usuarios_credenciais",
        "configuracoes_plantao",
        "producoes_ambulatoriais",
        "paciente_passkeys",
        "agenda_disponibilidades",
        "agendamentos",
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
    """Ensure clean tables before and after each test."""
    from tests.helpers import clean_database_tables

    await clean_database_tables()
    yield
    await clean_database_tables()


@pytest.mark.asyncio
async def test_migration_creates_all_single_platform_tables() -> None:
    """Verify that alembic upgrade head creates all expected single-platform tables."""
    async with get_engine().connect() as conn:
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
    assert "organizacoes" not in existing_tables


@pytest.mark.asyncio
async def test_zero_rls_policies_and_zero_organizacao_id_columns() -> None:
    """Verify no table has organizacao_id column and pg_policies is empty."""
    async with get_engine().connect() as conn:
        cols_res = await conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND column_name = 'organizacao_id';
                """
            )
        )
        org_cols = [row[0] for row in cols_res.fetchall()]

        policies_res = await conn.execute(
            text(
                """
                SELECT policyname
                FROM pg_policies
                WHERE schemaname = 'public';
                """
            )
        )
        policies = [row[0] for row in policies_res.fetchall()]

    assert org_cols == []
    assert policies == []


@pytest.mark.asyncio
async def test_gen_uuidv7_creates_valid_rfc9562_uuid() -> None:
    """Verify that PostgreSQL gen_uuidv7() generates RFC 9562 UUIDv7 values."""
    async with get_engine().connect() as conn:
        result = await conn.execute(text("SELECT gen_uuidv7();"))
        generated_uuid_str = result.scalar()

    assert generated_uuid_str is not None
    parsed_uuid = UUID(str(generated_uuid_str))
    assert parsed_uuid.version == 7


@pytest.mark.asyncio
async def test_partial_unique_indexes_on_pacientes() -> None:
    """Verify global partial unique indexes uq_paciente_cpf and uq_paciente_cns."""
    async with get_engine().connect() as conn:
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

    assert "uq_paciente_cpf" in indexes
    assert "WHERE (cpf IS NOT NULL)" in indexes["uq_paciente_cpf"]
    assert "uq_paciente_org_cpf" not in indexes

    assert "uq_paciente_cns" in indexes
    assert "WHERE (cns IS NOT NULL)" in indexes["uq_paciente_cns"]
    assert "uq_paciente_org_cns" not in indexes


@pytest.mark.asyncio
async def test_check_constraints_registered() -> None:
    """Verify critical check constraints on clinical aggregate tables."""
    async with get_engine().connect() as conn:
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
        "chk_configuracoes_unidade_singleton",
        "chk_configuracoes_plantao_singleton",
        "chk_documento_paciente_obrigatorio",
        "chk_atendimento_status",
        "chk_atendimento_prioridade",
        "chk_triagem_prioridade",
        "chk_documentos_tipo",
        "chk_documentos_sha256_len",
        "chk_audit_ator_tipo",
        "chk_config_plantao_alpha",
        "chk_config_plantao_tma",
        "chk_config_plantao_ring",
        "chk_config_plantao_modo",
        "chk_agenda_disp_dia_semana",
        "chk_agenda_disp_horarios",
        "chk_agenda_disp_duracao",
        "chk_agendamento_slot_valido",
        "chk_agendamento_status",
    }
    assert expected_checks.issubset(constraints)


@pytest.mark.asyncio
async def test_singleton_constraints_on_unidade_and_plantao() -> None:
    """Verify singleton_guard prevents inserting second row or false guard."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO configuracoes_unidade (cnpj, razao_social, nome_fantasia)
                VALUES ('11223344000188', 'Hospital Municipal', 'MediSync');
                """
            )
        )
        with pytest.raises(DBAPIError):
            await conn.execute(
                text(
                    """
                    INSERT INTO configuracoes_unidade
                        (cnpj, razao_social, nome_fantasia)
                    VALUES ('99887766000155', 'Outro Hospital', 'Outro');
                    """
                )
            )

    async with get_engine().begin() as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(
                text(
                    """
                    INSERT INTO configuracoes_unidade
                        (singleton_guard, cnpj, razao_social, nome_fantasia)
                    VALUES (false, '11223344000188', 'Hospital Municipal', 'MediSync');
                    """
                )
            )

    async with get_engine().begin() as conn:
        await conn.execute(text("INSERT INTO configuracoes_plantao DEFAULT VALUES;"))
        with pytest.raises(DBAPIError):
            await conn.execute(
                text("INSERT INTO configuracoes_plantao DEFAULT VALUES;")
            )


@pytest.mark.asyncio
async def test_audit_immutable_trigger_blocks_mutations() -> None:
    """Verify ADR-007 anti-tampering trigger blocks UPDATE on audit_events."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO pacientes (id, cpf, data_nascimento, telefone)
                VALUES (
                    '01a00000-0000-7000-8000-000000000011',
                    '88881111888',
                    '1985-05-15',
                    '11988881111'
                )
                ON CONFLICT DO NOTHING;

                INSERT INTO atendimentos (id, paciente_id, status)
                VALUES (
                    '01a00000-0000-7000-8000-000000000012',
                    '01a00000-0000-7000-8000-000000000011',
                    'TRIADO_AGUARDANDO_ELEGIBILIDADE'
                )
                ON CONFLICT DO NOTHING;

                INSERT INTO audit_events (
                    id, atendimento_id, ator_tipo, ator_papel, tipo_evento
                )
                VALUES (
                    '01a00000-0000-7000-8000-000000000013',
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
    await asyncio.to_thread(_run_alembic_downgrade_base)

    async with get_engine().connect() as conn:
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

    await asyncio.to_thread(_run_alembic_upgrade_head)

    async with get_engine().connect() as conn:
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
