"""Single canonical S3 key builder for clinical documents."""

from uuid import UUID


def build_signed_document_key(
    organizacao_id: int, atendimento_id: UUID, documento_id: UUID
) -> str:
    """Build canonical signed-document S3 key (single source of truth)."""
    return (
        f"orgs/{organizacao_id}/consultations/{atendimento_id}/"
        f"documents/{documento_id}.pdf"
    )
