"""Add nome_social column to pacientes table for CFM 1.821/2007 compliance.

Revision ID: 0005_paciente_nome_social
Revises: 0004_evolucao_finalizado_em
Create Date: 2026-10-11 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_paciente_nome_social"
down_revision: str | None = "0004_evolucao_finalizado_em"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pacientes",
        sa.Column("nome_social", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pacientes", "nome_social")
