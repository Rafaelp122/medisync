"""Unit tests for centralized tenant dependency (src.core.dependencies)."""

import pytest
from src.core.context import tenant_context
from src.core.dependencies import (
    TenantInvalidoError,
    get_optional_tenant_id,
    get_required_tenant_id,
)
from src.core.errors import ValidationError
from src.modules.auth.presentation.helpers import resolve_login_tenant_id


@pytest.mark.asyncio
async def test_get_required_tenant_id_sem_contexto_levanta_400() -> None:
    """Sem tenant no contexto -> TenantInvalidoError 400 RFC7807."""
    with tenant_context(None), pytest.raises(TenantInvalidoError) as exc_info:
        await get_required_tenant_id()

    err = exc_info.value
    assert err.status_code == 400
    assert err.code == "TENANT_INVALIDO"
    assert err.title == "Organização Inválida"


@pytest.mark.asyncio
async def test_get_required_tenant_id_com_contexto_retorna_42() -> None:
    """Com tenant_context(42) -> retorna 42."""
    with tenant_context(42):
        assert await get_required_tenant_id() == 42


@pytest.mark.asyncio
async def test_get_required_tenant_id_nao_positivo_levanta_400() -> None:
    """Contexto 0 ou negativo -> TenantInvalidoError 400."""
    for invalid in (0, -5):
        with tenant_context(invalid), pytest.raises(TenantInvalidoError) as exc_info:
            await get_required_tenant_id()
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "TENANT_INVALIDO"


@pytest.mark.asyncio
async def test_get_optional_tenant_id() -> None:
    """Optional retorna None sem contexto e valor com contexto."""
    with tenant_context(None):
        assert await get_optional_tenant_id() is None

    with tenant_context(7):
        assert await get_optional_tenant_id() == 7


@pytest.mark.asyncio
async def test_get_optional_tenant_id_nao_positivo_retorna_none() -> None:
    """Optional retorna None para contexto 0 ou negativo."""
    for invalid in (0, -3):
        with tenant_context(invalid):
            assert await get_optional_tenant_id() is None


def test_identity_tenant_error_alias_core() -> None:
    """identity.domain TenantInvalidoError deve ser alias do core."""
    from src.core.dependencies import TenantInvalidoError as CoreError
    from src.core.errors import TenantInvalidoError as ErrorsError
    from src.modules.identity.domain.exceptions import (
        TenantInvalidoError as IdentityError,
    )

    assert IdentityError is CoreError
    assert IdentityError is ErrorsError
    assert CoreError.status_code == 400
    assert CoreError.title == "Organização Inválida"
    assert CoreError.code == "TENANT_INVALIDO"


def test_resolve_login_tenant_id_prefere_body() -> None:
    """Body válido tem precedência sobre contexto."""
    assert resolve_login_tenant_id(5, 10) == 5
    assert resolve_login_tenant_id(5, None) == 5


def test_resolve_login_tenant_id_body_invalido_levanta_422() -> None:
    """Body 0 ou negativo -> ValidationError 422 mesmo com contexto válido."""
    for invalid in (-5, 0):
        with pytest.raises(ValidationError) as exc_info:
            resolve_login_tenant_id(invalid, 10)
        assert exc_info.value.status_code == 422


def test_resolve_login_tenant_id_fallback_contexto() -> None:
    """Sem body -> usa contexto quando positivo."""
    assert resolve_login_tenant_id(None, 10) == 10


def test_resolve_login_tenant_id_ambos_ausentes_levanta_422() -> None:
    """Sem body e sem contexto (ou contexto não-positivo) -> 422."""
    for ctx in (None, 0, -2):
        with pytest.raises(ValidationError) as exc_info:
            resolve_login_tenant_id(None, ctx)
        assert exc_info.value.status_code == 422
