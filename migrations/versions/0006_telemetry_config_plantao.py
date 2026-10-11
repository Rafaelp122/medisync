"""Add configuracoes_plantao table for shift telemetry configuration.

Revision ID: 0006_telemetry_config_plantao
Revises: 0005_paciente_nome_social
Create Date: 2026-10-11 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_telemetry_config_plantao"
down_revision: str | None = "0005_paciente_nome_social"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Criação da tabela configuracoes_plantao
    op.create_table(
        "configuracoes_plantao",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_uuidv7()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "medicos_ativos_planejados",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "alpha_backpressure",
            sa.Numeric(precision=4, scale=2),
            server_default="1.25",
            nullable=False,
        ),
        sa.Column(
            "cota_diaria_maxima",
            sa.Integer(),
            server_default="300",
            nullable=True,
        ),
        sa.Column(
            "tma_padrao_segundos",
            sa.Integer(),
            server_default="600",
            nullable=False,
        ),
        sa.Column(
            "tempo_tolerancia_ring_segundos",
            sa.Integer(),
            server_default="45",
            nullable=False,
        ),
        sa.Column(
            "modo_operacao",
            sa.String(length=32),
            server_default="SUS",
            nullable=False,
        ),
        sa.Column(
            "sla_minutos_nivel_1",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "sla_minutos_nivel_2",
            sa.Integer(),
            server_default="10",
            nullable=False,
        ),
        sa.Column(
            "sla_minutos_nivel_3",
            sa.Integer(),
            server_default="60",
            nullable=False,
        ),
        sa.Column(
            "sla_minutos_nivel_4",
            sa.Integer(),
            server_default="120",
            nullable=False,
        ),
        sa.Column(
            "sla_minutos_nivel_5",
            sa.Integer(),
            server_default="240",
            nullable=False,
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
        sa.Column("atualizado_por_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name="fk_configuracoes_plantao_organizacao_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_configuracoes_plantao"),
        sa.UniqueConstraint("organizacao_id", name="uq_configuracoes_plantao_org"),
        sa.CheckConstraint(
            "alpha_backpressure >= 1.20 AND alpha_backpressure <= 1.30",
            name="chk_config_plantao_alpha",
        ),
        sa.CheckConstraint(
            "tma_padrao_segundos >= 60",
            name="chk_config_plantao_tma",
        ),
        sa.CheckConstraint(
            "tempo_tolerancia_ring_segundos >= 10",
            name="chk_config_plantao_ring",
        ),
        sa.CheckConstraint(
            "modo_operacao IN ('SUS', 'PRIVADO')",
            name="chk_config_plantao_modo",
        ),
    )

    # 2. RLS obrigatório (ADR-003)
    op.execute("ALTER TABLE configuracoes_plantao ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE configuracoes_plantao FORCE ROW LEVEL SECURITY;")
    _predicate = (
        "organizacao_id = "
        "NULLIF(current_setting('app.current_tenant_id', true), '')::bigint"
    )
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_configuracoes_plantao
            ON configuracoes_plantao
            USING ({_predicate})
            WITH CHECK ({_predicate});
        """
    )

    # 3. Concessão de permissões DCL para medisync_app
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'medisync_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON configuracoes_plantao TO medisync_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_configuracoes_plantao "
        "ON configuracoes_plantao;"
    )
    op.execute(
        "ALTER TABLE IF EXISTS configuracoes_plantao NO FORCE ROW LEVEL SECURITY;"
    )
    op.execute(
        "ALTER TABLE IF EXISTS configuracoes_plantao DISABLE ROW LEVEL SECURITY;"
    )
    op.drop_table("configuracoes_plantao", if_exists=True)
