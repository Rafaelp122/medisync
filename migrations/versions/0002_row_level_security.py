"""Apply Row-Level Security (RLS) on all 9 multi-tenant tables and audit DCL.

Revision ID: 0002_row_level_security
Revises: 0001_initial_schema
Create Date: 2026-10-02 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_row_level_security"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MULTI_TENANT_TABLES: tuple[str, ...] = (
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

_POLICY_PREDICATE: str = (
    "organizacao_id = "
    "NULLIF(current_setting('app.current_tenant_id', true), '')::bigint"
)


def upgrade() -> None:
    # 1. Criação do papel de aplicação medisync_app com NOBYPASSRLS
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'medisync_app') THEN
                CREATE ROLE medisync_app NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )

    # 2. Concessão de permissões DCL básicas para medisync_app
    op.execute(
        """
        GRANT USAGE ON SCHEMA public TO medisync_app;
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON ALL TABLES IN SCHEMA public TO medisync_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO medisync_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO medisync_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT USAGE, SELECT ON SEQUENCES TO medisync_app;
        """
    )

    # 3. Blindagem DCL da trilha de auditoria (ADR-007)
    op.execute(
        """
        REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM PUBLIC, medisync_app;
        GRANT SELECT, INSERT ON audit_events TO medisync_app;
        """
    )

    # 4. Ativação e imposição forçada de RLS nas 9 tabelas multi-tenant (ADR-003)
    for table_name in _MULTI_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;")

    # 5. Criação de políticas de isolamento tenant_isolation_*
    for table_name in _MULTI_TENANT_TABLES:
        policy_name = f"tenant_isolation_{table_name}"
        op.execute(
            f"""
            CREATE POLICY {policy_name} ON {table_name}
                USING ({_POLICY_PREDICATE})
                WITH CHECK ({_POLICY_PREDICATE});
            """
        )


def downgrade() -> None:
    # 1. Remoção de políticas de isolamento
    for table_name in _MULTI_TENANT_TABLES:
        policy_name = f"tenant_isolation_{table_name}"
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name};")

    # 2. Desativação de RLS nas 9 tabelas
    for table_name in _MULTI_TENANT_TABLES:
        op.execute(f"ALTER TABLE IF EXISTS {table_name} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE IF EXISTS {table_name} DISABLE ROW LEVEL SECURITY;")

    # 3. Restabelecimento de permissões padrão em audit_events
    op.execute(
        """
        GRANT UPDATE, DELETE ON audit_events TO medisync_app;
        """
    )
