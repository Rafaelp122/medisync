"""Create paciente_passkeys table and clinical liveness proof columns.

Revision ID: 0014_passkeys_and_liveness
Revises: 0013_evolucao_cfm_identidade
Create Date: 2026-11-15 10:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_passkeys_and_liveness"
down_revision: str | None = "0013_evolucao_cfm_identidade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paciente_passkeys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("paciente_id", sa.UUID(), nullable=False),
        sa.Column("credential_id", sa.String(length=512), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column(
            "sign_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("device_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organizacao_id",
            "credential_id",
            name="uq_paciente_passkeys_org_cred",
        ),
    )
    op.create_index(
        "ix_paciente_passkeys_organizacao_id",
        "paciente_passkeys",
        ["organizacao_id"],
    )
    op.create_index(
        "ix_paciente_passkeys_paciente_id", "paciente_passkeys", ["paciente_id"]
    )
    op.create_index(
        "ix_paciente_passkeys_credential_id", "paciente_passkeys", ["credential_id"]
    )
    op.create_index(
        "idx_paciente_passkeys_paciente",
        "paciente_passkeys",
        ["organizacao_id", "paciente_id"],
    )

    op.execute("ALTER TABLE paciente_passkeys ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE paciente_passkeys FORCE ROW LEVEL SECURITY;")

    predicate = (
        "organizacao_id = "
        "NULLIF(current_setting('app.current_tenant_id', true), '')::bigint"
    )
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_paciente_passkeys
            ON paciente_passkeys
            USING ({predicate})
            WITH CHECK ({predicate});
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'medisync_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON paciente_passkeys TO medisync_app;
            END IF;
        END
        $$;
        """
    )

    op.add_column(
        "documentos_clinicos",
        sa.Column(
            "liveness_verificacao_hash",
            sa.String(length=128),
            nullable=True,
        ),
    )
    op.add_column(
        "documentos_clinicos",
        sa.Column(
            "justificativa_excecao_liveness",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("documentos_clinicos", "justificativa_excecao_liveness")
    op.drop_column("documentos_clinicos", "liveness_verificacao_hash")

    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_paciente_passkeys ON paciente_passkeys;"
    )
    op.execute("ALTER TABLE IF EXISTS paciente_passkeys NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE IF EXISTS paciente_passkeys DISABLE ROW LEVEL SECURITY;")
    op.drop_index("idx_paciente_passkeys_paciente", table_name="paciente_passkeys")
    op.drop_index("ix_paciente_passkeys_credential_id", table_name="paciente_passkeys")
    op.drop_index("ix_paciente_passkeys_paciente_id", table_name="paciente_passkeys")
    op.drop_index("ix_paciente_passkeys_organizacao_id", table_name="paciente_passkeys")
    op.drop_table("paciente_passkeys")
