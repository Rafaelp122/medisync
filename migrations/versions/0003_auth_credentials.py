"""Create usuarios_credenciais table with Argon2id hash, lockout, and RLS.

Revision ID: 0003_auth_credentials
Revises: 0002_row_level_security
Create Date: 2026-10-03 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_auth_credentials"
down_revision: str | None = "0002_row_level_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY_PREDICATE: str = (
    "organizacao_id = "
    "NULLIF(current_setting('app.current_tenant_id', true), '')::bigint"
)


def upgrade() -> None:
    # 1. Criação da tabela de credenciais de autenticação
    op.create_table(
        "usuarios_credenciais",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("identificador", sa.String(length=255), nullable=False),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column("papel", sa.String(length=32), nullable=False),
        sa.Column(
            "ativo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "falhas_login_consecutivas",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "bloqueado_ate",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_usuarios_credenciais_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usuarios_credenciais"),
        sa.UniqueConstraint(
            "organizacao_id",
            "identificador",
            name="uq_usuarios_credenciais_org_identificador",
        ),
    )

    # 2. Índices de busca e filtros operacionais
    op.create_index(
        "idx_usuarios_credenciais_org_papel",
        "usuarios_credenciais",
        ["organizacao_id", "papel"],
        unique=False,
    )
    op.create_index(
        "idx_usuarios_credenciais_usuario_id",
        "usuarios_credenciais",
        ["usuario_id"],
        unique=False,
    )

    # 3. Habilitação de RLS e concessão de privilégios para medisync_app
    op.execute("ALTER TABLE usuarios_credenciais ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE usuarios_credenciais FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_usuarios_credenciais ON usuarios_credenciais
            USING ({_POLICY_PREDICATE})
            WITH CHECK ({_POLICY_PREDICATE});
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'medisync_app') THEN
                CREATE ROLE medisync_app NOBYPASSRLS;
            END IF;
            GRANT USAGE ON SCHEMA public TO medisync_app;
            GRANT SELECT, INSERT, UPDATE, DELETE
                ON usuarios_credenciais TO medisync_app;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_usuarios_credenciais "
        "ON usuarios_credenciais;"
    )
    op.drop_index(
        "idx_usuarios_credenciais_usuario_id",
        table_name="usuarios_credenciais",
    )
    op.drop_index(
        "idx_usuarios_credenciais_org_papel",
        table_name="usuarios_credenciais",
    )
    op.drop_table("usuarios_credenciais")
