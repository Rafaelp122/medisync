"""Clinical AI governance (CFM 2.454/2026), antifraud duration lock,
and MFA credentials.

Revision ID: 0011_clinical_ai_gov_and_mfa
Revises: 0010_sus_organizations_cnes
Create Date: 2026-11-02 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_clinical_ai_gov_and_mfa"
down_revision: str | None = "0010_sus_organizations_cnes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Colunas de governança de IA e SIGTAP na tabela evolucoes_clinicas
    op.add_column(
        "evolucoes_clinicas",
        sa.Column(
            "codigo_sigtap",
            sa.String(length=16),
            nullable=False,
            server_default="03.01.01.025-0",
        ),
    )
    op.add_column(
        "evolucoes_clinicas",
        sa.Column(
            "ia_utilizada",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "evolucoes_clinicas",
        sa.Column("ia_modelo", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "evolucoes_clinicas",
        sa.Column("ia_sugestao_bruta", sa.Text(), nullable=True),
    )
    op.add_column(
        "evolucoes_clinicas",
        sa.Column("ia_diff_modificacao", sa.Text(), nullable=True),
    )
    op.add_column(
        "evolucoes_clinicas",
        sa.Column(
            "ia_ratificada_pelo_medico",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # 2. Coluna de justificativa temporal anti-fraude na tabela documentos_clinicos
    op.add_column(
        "documentos_clinicos",
        sa.Column("justificativa_tempo_inferior", sa.Text(), nullable=True),
    )

    # 3. Colunas de MFA TOTP na tabela usuarios_credenciais
    op.add_column(
        "usuarios_credenciais",
        sa.Column("mfa_secret", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "usuarios_credenciais",
        sa.Column(
            "mfa_ativo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    # 3. Reverter usuarios_credenciais
    op.drop_column("usuarios_credenciais", "mfa_ativo")
    op.drop_column("usuarios_credenciais", "mfa_secret")

    # 2. Reverter documentos_clinicos
    op.drop_column("documentos_clinicos", "justificativa_tempo_inferior")

    # 1. Reverter evolucoes_clinicas
    op.drop_column("evolucoes_clinicas", "ia_ratificada_pelo_medico")
    op.drop_column("evolucoes_clinicas", "ia_diff_modificacao")
    op.drop_column("evolucoes_clinicas", "ia_sugestao_bruta")
    op.drop_column("evolucoes_clinicas", "ia_modelo")
    op.drop_column("evolucoes_clinicas", "ia_utilizada")
    op.drop_column("evolucoes_clinicas", "codigo_sigtap")
