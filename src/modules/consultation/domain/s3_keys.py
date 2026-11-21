"""Single canonical S3 key builder for clinical documents."""

from uuid import UUID


def build_signed_document_key(atendimento_id: UUID, documento_id: UUID) -> str:
    """Constrói a chave S3 canônica para documento clínico assinado em plataforma única.

    Regras: docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md e
    docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md.
    """
    return f"consultations/{atendimento_id}/documents/{documento_id}.pdf"
