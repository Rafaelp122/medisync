"""Decouple atendimento_id in audit_events and add multi-tenant composite index.

Revision ID: 0007_audit_events_decoupling
Revises: 0006_telemetry_config_plantao
Create Date: 2026-10-30 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_audit_events_decoupling"
down_revision: str | None = "0006_telemetry_config_plantao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Tornar atendimento_id opcional (nullable=True) para permitir
    # auditoria transversal de segurança
    op.alter_column(
        "audit_events",
        "atendimento_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # 2. Criar índice composto multi-tenant sob RLS (ADR-003 / ADR-007)
    op.create_index(
        "idx_audit_org_atendimento",
        "audit_events",
        ["organizacao_id", "atendimento_id", "registrado_em"],
    )


def downgrade() -> None:
    op.drop_index("idx_audit_org_atendimento", table_name="audit_events")
    op.alter_column(
        "audit_events",
        "atendimento_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
