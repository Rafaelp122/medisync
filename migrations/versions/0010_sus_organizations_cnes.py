"""Add CNES, tipo_unidade_sus and ibge_municipio to organizacoes (ADR-012).

Revision ID: 0010_sus_organizations_cnes
Revises: 0009_pep_forensic_lifecycle
Create Date: 2026-11-02 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_sus_organizations_cnes"
down_revision: str | None = "0009_pep_forensic_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Adicionar colunas públicas SUS
    op.add_column(
        "organizacoes",
        sa.Column("cnes", sa.String(length=7), nullable=True),
    )
    op.add_column(
        "organizacoes",
        sa.Column(
            "tipo_unidade_sus",
            sa.String(length=64),
            nullable=False,
            server_default="UPA_DIGITAL_24H",
        ),
    )
    op.add_column(
        "organizacoes",
        sa.Column("ibge_municipio", sa.String(length=7), nullable=True),
    )

    # 2. Tornar o default de modo_publico_sus como true
    op.alter_column(
        "organizacoes",
        "modo_publico_sus",
        server_default=sa.text("true"),
    )


def downgrade() -> None:
    op.alter_column(
        "organizacoes",
        "modo_publico_sus",
        server_default=sa.text("false"),
    )
    op.drop_column("organizacoes", "ibge_municipio")
    op.drop_column("organizacoes", "tipo_unidade_sus")
    op.drop_column("organizacoes", "cnes")
