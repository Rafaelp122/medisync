"""Single canonical S3 key builder for clinical documents."""

from uuid import UUID


def build_signed_document_key(atendimento_id: UUID, documento_id: UUID) -> str:
    """Build canonical signed-document S3 key (single source of truth)."""
    return f"consultations/{atendimento_id}/documents/{documento_id}.pdf"
