"""Add escala_dor to triagens, drop duplicate index, and add indices to atendimentos.

Revision ID: 0008_queue_triage_clinical_indices
Revises: 0007_audit_events_decoupling
Create Date: 2026-10-30 20:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_queue_triage_clinical_indices"
down_revision: str | None = "0007_audit_events_decoupling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Adicionar escala_dor em triagens com valor padrao 0
    op.add_column(
        "triagens",
        sa.Column("escala_dor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "chk_triagem_escala_dor",
        "triagens",
        "escala_dor BETWEEN 0 AND 10",
    )

    # 2. Remover indice duplicado em triagens (coberto por uq_triagens_atendimento_id)
    op.drop_index("idx_triagens_atendimento", table_name="triagens")

    # 3. Adicionar indices B-Tree de chaves estrangeiras em atendimentos
    op.create_index(
        "idx_atendimentos_org_paciente",
        "atendimentos",
        ["organizacao_id", "paciente_id"],
    )
    op.create_index(
        "idx_atendimentos_medico",
        "atendimentos",
        ["medico_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_atendimentos_medico", table_name="atendimentos")
    op.drop_index("idx_atendimentos_org_paciente", table_name="atendimentos")
    op.create_index(
        "idx_triagens_atendimento",
        "triagens",
        ["atendimento_id"],
    )
    op.drop_constraint("chk_triagem_escala_dor", "triagens", type_="check")
    op.drop_column("triagens", "escala_dor")
