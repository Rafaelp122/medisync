"""Create agenda_disponibilidades and agendamentos tables with RLS.

Revision ID: 0015_scheduling_tables
Revises: 0014_passkeys_and_liveness
Create Date: 2026-11-16 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_scheduling_tables"
down_revision: str | None = "0014_passkeys_and_liveness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEDULING_TABLES: tuple[str, ...] = (
    "agenda_disponibilidades",
    "agendamentos",
)


def upgrade() -> None:
    op.create_table(
        "agenda_disponibilidades",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("profissional_id", sa.UUID(), nullable=False),
        sa.Column("especialidade", sa.String(length=40), nullable=False),
        sa.Column("dia_semana", sa.Integer(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fim", sa.Time(), nullable=False),
        sa.Column("duracao_minutos", sa.Integer(), nullable=False),
        sa.Column(
            "ativo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.CheckConstraint(
            "dia_semana BETWEEN 0 AND 6",
            name="chk_agenda_disp_dia_semana",
        ),
        sa.CheckConstraint(
            "hora_fim > hora_inicio",
            name="chk_agenda_disp_horarios",
        ),
        sa.CheckConstraint(
            "duracao_minutos BETWEEN 15 AND 120",
            name="chk_agenda_disp_duracao",
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profissional_id"],
            ["profissionais.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_agenda_disp_org_esp",
        "agenda_disponibilidades",
        ["organizacao_id", "especialidade", "dia_semana"],
    )
    op.create_index(
        "idx_agenda_disp_prof",
        "agenda_disponibilidades",
        ["organizacao_id", "profissional_id"],
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")

    op.create_table(
        "agendamentos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("paciente_id", sa.UUID(), nullable=False),
        sa.Column("profissional_id", sa.UUID(), nullable=False),
        sa.Column("especialidade", sa.String(length=40), nullable=False),
        sa.Column("slot_inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_fim", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="AGENDADO",
        ),
        sa.Column("observacoes", sa.String(length=500), nullable=True),
        sa.Column("atendimento_id", sa.UUID(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "slot_fim > slot_inicio",
            name="chk_agendamento_slot_valido",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'AGENDADO', 'CONFIRMADO', 'EM_ATENDIMENTO', "
            "'CONCLUIDO', 'CANCELADO', 'FALTA'"
            ")",
            name="chk_agendamento_status",
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["pacientes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profissional_id"],
            ["profissionais.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["atendimento_id"],
            ["atendimentos.id"],
            ondelete="RESTRICT",
        ),
        postgresql.ExcludeConstraint(
            ("organizacao_id", "="),
            ("profissional_id", "="),
            (
                sa.func.tstzrange(
                    sa.column("slot_inicio"),
                    sa.column("slot_fim"),
                    "[)",
                ),
                "&&",
            ),
            name="excl_agendamento_slot_ativo",
            using="gist",
            where=sa.text("status NOT IN ('CANCELADO', 'FALTA')"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_agendamento_slot_ativo",
        "agendamentos",
        ["organizacao_id", "profissional_id", "slot_inicio"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('CANCELADO', 'FALTA')"),
    )
    op.create_index(
        "uq_agendamento_atendimento_id",
        "agendamentos",
        ["atendimento_id"],
        unique=True,
        postgresql_where=sa.text("atendimento_id IS NOT NULL"),
    )
    op.create_index(
        "idx_agendamentos_org_paciente",
        "agendamentos",
        ["organizacao_id", "paciente_id", "slot_inicio"],
    )
    op.create_index(
        "idx_agendamentos_org_profissional",
        "agendamentos",
        ["organizacao_id", "profissional_id", "slot_inicio"],
    )

    predicate = (
        "organizacao_id = "
        "NULLIF(current_setting('app.current_tenant_id', true), '')::bigint"
    )
    for table_name in _SCHEDULING_TABLES:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table_name}
                ON {table_name}
                USING ({predicate})
                WITH CHECK ({predicate});
            """
        )
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'medisync_app') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE
                        ON {table_name} TO medisync_app;
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    for table_name in reversed(_SCHEDULING_TABLES):
        op.execute(
            f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name};"
        )
        op.execute(f"ALTER TABLE IF EXISTS {table_name} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE IF EXISTS {table_name} DISABLE ROW LEVEL SECURITY;")

    op.drop_index("idx_agendamentos_org_profissional", table_name="agendamentos")
    op.drop_index("idx_agendamentos_org_paciente", table_name="agendamentos")
    op.drop_index(
        "uq_agendamento_atendimento_id",
        table_name="agendamentos",
        if_exists=True,
    )
    op.drop_index("uq_agendamento_slot_ativo", table_name="agendamentos")
    op.drop_table("agendamentos")

    op.drop_index("idx_agenda_disp_prof", table_name="agenda_disponibilidades")
    op.drop_index("idx_agenda_disp_org_esp", table_name="agenda_disponibilidades")
    op.drop_table("agenda_disponibilidades")
