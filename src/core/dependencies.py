"""Centralized multi-tenant FastAPI dependencies (single tenant policy)."""

from typing import Annotated

from fastapi import Depends

from src.core.context import get_current_tenant_id
from src.core.errors import TenantInvalidoError

__all__ = [
    "OptionalTenantDep",
    "TenantDep",
    "TenantInvalidoError",
    "get_optional_tenant_id",
    "get_required_tenant_id",
]


async def get_required_tenant_id() -> int:
    """Return active tenant ID or raise 400 when missing/non-positive."""
    tenant_id = get_current_tenant_id()
    if tenant_id is None or tenant_id <= 0:
        raise TenantInvalidoError()
    return tenant_id


async def get_optional_tenant_id() -> int | None:
    """Return active tenant ID or None when missing/non-positive."""
    tenant_id = get_current_tenant_id()
    if tenant_id is not None and tenant_id <= 0:
        return None
    return tenant_id


TenantDep = Annotated[int, Depends(get_required_tenant_id)]
OptionalTenantDep = Annotated[int | None, Depends(get_optional_tenant_id)]
