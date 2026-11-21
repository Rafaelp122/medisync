"""Add outorga_tcle column to dependentes for pediatric TCLE consent (RN-IDE-05).

Revision ID: 0002_add_outorga_tcle_dependentes
Revises: 0001_initial_schema
Create Date: 2026-11-21 10:52:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_outorga_tcle_dependentes"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dependentes",
        sa.Column(
            "outorga_tcle",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("dependentes", "outorga_tcle")
