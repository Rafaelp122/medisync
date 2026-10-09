"""Add finalizado_em timestamp to evolucoes_clinicas for deontological PEP immutability.

Revision ID: 0004_evolucao_finalizado_em
Revises: 0003_auth_credentials
Create Date: 2026-10-08 19:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_evolucao_finalizado_em"
down_revision: str | None = "0003_auth_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evolucoes_clinicas",
        sa.Column("finalizado_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evolucoes_clinicas", "finalizado_em")
