"""Presentation helpers for authentication endpoints."""

from src.core.errors import ValidationError


def resolve_login_tenant_id(
    body_org_id: int | None, context_tenant_id: int | None
) -> int:
    """Prefer body organizacao_id over header context; raise 422 if neither."""
    org_id = body_org_id or context_tenant_id
    if not org_id:
        raise ValidationError(
            "Identificador da organização (tenant) não informado "
            "(preencha no corpo ou no cabeçalho X-Tenant-ID)."
        )
    return org_id
