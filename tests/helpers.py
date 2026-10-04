"""Shared test helpers and database utilities."""

from sqlalchemy import text
from src.core.database import engine

CLEAN_TABLES_SQL = text(
    "TRUNCATE TABLE documento_itens, documentos_clinicos, evolucoes_clinicas, "
    "triagens, audit_events, atendimentos, dependentes, pacientes, "
    "profissionais, organizacoes, usuarios_credenciais CASCADE;"
)


async def clean_database_tables() -> None:
    """Safely truncate all domain tables respecting foreign keys."""
    async with engine.begin() as conn:
        await conn.execute(CLEAN_TABLES_SQL)
