"""Unit tests for centralized tenant dependency (src.core.dependencies)."""

import pytest
from src.core.context import tenant_context


@pytest.mark.asyncio
async def test_get_required_tenant_id_sem_contexto_levanta_400() -> None:
    """Sem tenant no contexto -> TenantInvalidoError 400 RFC7807."""
    from src.core.dependencies import TenantInvalidoError, get_required_tenant_id

    with tenant_context(None), pytest.raises(TenantInvalidoError) as exc_info:
        await get_required_tenant_id()

    err = exc_info.value
    assert err.status_code == 400
    assert err.code == "TENANT_INVALIDO"
    assert err.title == "Organização Inválida"


@pytest.mark.asyncio
async def test_get_required_tenant_id_com_contexto_retorna_42() -> None:
    """Com tenant_context(42) -> retorna 42."""
    from src.core.dependencies import get_required_tenant_id

    with tenant_context(42):
        assert await get_required_tenant_id() == 42


@pytest.mark.asyncio
async def test_get_optional_tenant_id() -> None:
    """Optional retorna None sem contexto e valor com contexto."""
    from src.core.dependencies import get_optional_tenant_id

    with tenant_context(None):
        assert await get_optional_tenant_id() is None

    with tenant_context(7):
        assert await get_optional_tenant_id() == 7


def test_identity_tenant_error_alias_core() -> None:
    """identity.domain TenantInvalidoError deve ser alias do core."""
    from src.core.dependencies import TenantInvalidoError as CoreError
    from src.modules.identity.domain.exceptions import (
        TenantInvalidoError as IdentityError,
    )

    assert IdentityError is CoreError
    assert CoreError.status_code == 400
    assert CoreError.title == "Organização Inválida"
    assert CoreError.code == "TENANT_INVALIDO"
