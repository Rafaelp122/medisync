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


def is_signed_document_key(chave_s3: str, organizacao_id: int) -> bool:
    """Check if storage key follows signed-document canonical prefix."""
    return chave_s3.startswith(f"orgs/{organizacao_id}/consultations/")
