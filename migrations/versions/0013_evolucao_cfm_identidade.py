"""Add CFM 2.314/2022 patient identity verification columns to evolucoes_clinicas.

Revision ID: 0013_evolucao_cfm_identidade
Revises: 0012_producao_ambulatorial_bpa
Create Date: 2026-11-15 00:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_evolucao_cfm_identidade"
down_revision: str | None = "0012_producao_ambulatorial_bpa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evolucoes_clinicas",
        sa.Column(
            "identidade_verificada",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "evolucoes_clinicas",
        sa.Column(
            "tipo_documento_verificado",
            sa.String(length=16),
            nullable=True,
        ),
    )
    op.add_column(
        "evolucoes_clinicas",
        sa.Column(
            "justificativa_excecao_identidade",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("evolucoes_clinicas", "justificativa_excecao_identidade")
    op.drop_column("evolucoes_clinicas", "tipo_documento_verificado")
    op.drop_column("evolucoes_clinicas", "identidade_verificada")
