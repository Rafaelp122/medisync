"""Presentation helpers for authentication endpoints."""

from src.core.errors import ValidationError


def resolve_login_tenant_id(
    body_org_id: int | None, context_tenant_id: int | None
) -> int:
    """Prefer body organizacao_id over header context; raise 422 if neither."""
    if body_org_id is not None:
        if body_org_id <= 0:
            raise ValidationError(
                "Identificador da organização (tenant) deve ser positivo."
            )
        return body_org_id
    if context_tenant_id is not None and context_tenant_id > 0:
        return context_tenant_id
    raise ValidationError(
        "Identificador da organização (tenant) não informado "
        "(preencha no corpo ou no cabeçalho X-Tenant-ID)."
    )
