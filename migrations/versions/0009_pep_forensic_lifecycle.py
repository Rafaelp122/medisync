"""Add finalizado_em to PEP documents and unique constraint on evolucoes.

Revision ID: 0009_pep_forensic_lifecycle
Revises: 0008_queue_triage_clinical_indices
Create Date: 2026-10-30 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_pep_forensic_lifecycle"
down_revision: str | None = "0008_queue_triage_clinical_indices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Coluna finalizado_em em documentos_clinicos
    op.add_column(
        "documentos_clinicos",
        sa.Column("finalizado_em", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. sha256_hash e assinado_em anuláveis (rascunho antes da assinatura)
    op.alter_column(
        "documentos_clinicos",
        "sha256_hash",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.alter_column(
        "documentos_clinicos",
        "assinado_em",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )

    # 3. Atualizar constraint de tamanho de hash (NULL ou 64 caracteres)
    op.drop_constraint(
        "chk_documentos_sha256_len",
        "documentos_clinicos",
        type_="check",
    )
    op.create_check_constraint(
        "chk_documentos_sha256_len",
        "documentos_clinicos",
        "sha256_hash IS NULL OR length(sha256_hash) = 64",
    )

    # 4. Constraint única para evolução SOAP (1 evolução por atendimento)
    op.create_unique_constraint(
        "uq_evolucoes_clinicas_atendimento_id",
        "evolucoes_clinicas",
        ["atendimento_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_evolucoes_clinicas_atendimento_id",
        "evolucoes_clinicas",
        type_="unique",
    )
    op.drop_constraint(
        "chk_documentos_sha256_len",
        "documentos_clinicos",
        type_="check",
    )
    op.create_check_constraint(
        "chk_documentos_sha256_len",
        "documentos_clinicos",
        "length(sha256_hash) = 64",
    )
    op.alter_column(
        "documentos_clinicos",
        "assinado_em",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
    )
    op.alter_column(
        "documentos_clinicos",
        "sha256_hash",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.drop_column("documentos_clinicos", "finalizado_em")
