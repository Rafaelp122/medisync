"""Ambulatory production table for SUS BPA-I and SISAB consolidation.

Revision ID: 0012_producao_ambulatorial_bpa
Revises: 0011_clinical_ai_gov_and_mfa
Create Date: 2026-11-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_producao_ambulatorial_bpa"
down_revision: str | None = "0011_clinical_ai_gov_and_mfa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "producoes_ambulatoriais",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organizacao_id", sa.BigInteger(), nullable=False),
        sa.Column("atendimento_id", sa.UUID(), nullable=False),
        sa.Column("profissional_id", sa.UUID(), nullable=False),
        sa.Column("paciente_id", sa.UUID(), nullable=False),
        sa.Column("cnes", sa.String(length=7), nullable=False),
        sa.Column(
            "codigo_sigtap",
            sa.String(length=16),
            nullable=False,
            server_default="03.01.01.025-0",
        ),
        sa.Column(
            "carater_atendimento",
            sa.String(length=2),
            nullable=False,
            server_default="02",
        ),
        sa.Column("competencia", sa.String(length=6), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="CONSOLIDADO",
        ),
        sa.Column(
            "consolidado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["atendimento_id"], ["atendimentos.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"], ["organizacoes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["paciente_id"], ["pacientes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["profissional_id"], ["profissionais.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "atendimento_id", name="uq_producoes_ambulatoriais_atendimento_id"
        ),
    )
    op.create_index(
        "idx_producao_atendimento", "producoes_ambulatoriais", ["atendimento_id"]
    )
    op.create_index("idx_producao_org", "producoes_ambulatoriais", ["organizacao_id"])
    op.create_index(
        "idx_producao_competencia", "producoes_ambulatoriais", ["competencia"]
    )

    # Multi-tenant PostgreSQL RLS
    op.execute("ALTER TABLE producoes_ambulatoriais ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE producoes_ambulatoriais FORCE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS producoes_ambulatoriais NO FORCE ROW LEVEL SECURITY;"
    )
    op.execute(
        "ALTER TABLE IF EXISTS producoes_ambulatoriais DISABLE ROW LEVEL SECURITY;"
    )
    op.drop_index("idx_producao_competencia", table_name="producoes_ambulatoriais")
    op.drop_index("idx_producao_org", table_name="producoes_ambulatoriais")
    op.drop_index("idx_producao_atendimento", table_name="producoes_ambulatoriais")
    op.drop_table("producoes_ambulatoriais")
