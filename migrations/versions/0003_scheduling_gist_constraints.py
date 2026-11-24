"""Add GiST exclusion constraints on scheduling tables (Issue #166).

Revision ID: 0003_scheduling_gist_constraints
Revises: 0002_add_outorga_tcle_dependentes
Create Date: 2026-11-23 11:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_scheduling_gist_constraints"
down_revision: str | None = "0002_add_outorga_tcle_dependentes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")
    op.create_exclude_constraint(
        "excl_agenda_disp_sobreposicao",
        "agenda_disponibilidades",
        ("profissional_id", "="),
        ("dia_semana", "="),
        (
            sa.func.numrange(
                sa.func.extract("epoch", sa.column("hora_inicio")),
                sa.func.extract("epoch", sa.column("hora_fim")),
                "[)",
            ),
            "&&",
        ),
        using="gist",
        where=sa.text("ativo IS TRUE"),
    )
    op.create_exclude_constraint(
        "excl_agendamento_paciente_ativo",
        "agendamentos",
        ("paciente_id", "="),
        (
            sa.func.tstzrange(
                sa.column("slot_inicio"),
                sa.column("slot_fim"),
                "[)",
            ),
            "&&",
        ),
        using="gist",
        where=sa.text("status NOT IN ('CANCELADO', 'FALTA')"),
    )


def downgrade() -> None:
    op.drop_constraint(
        "excl_agendamento_paciente_ativo",
        "agendamentos",
        if_exists=True,
    )
    op.drop_constraint(
        "excl_agenda_disp_sobreposicao",
        "agenda_disponibilidades",
        if_exists=True,
    )
