"""Unit tests for shift telemetry authorization dependencies (ADR-001/Issue #87)."""

from uuid import uuid4

import pytest
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import Permission, Role
from src.core.errors import ForbiddenError
from src.modules.telemetry.presentation.dependencies import (
    require_telemetry_config_auth,
    require_telemetry_view_auth,
)


def _make_user(papel: Role | str) -> AuthenticatedUser:
    return AuthenticatedUser(
        usuario_id=uuid4(),
        organizacao_id=1,
        papel=str(papel.value if isinstance(papel, Role) else papel),
        token_id=uuid4(),
        raw_token="fake.jwt.token",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "papel",
    [Role.MEDICO, Role.GESTOR_UNIDADE, Role.ADMIN_GLOBAL],
)
async def test_require_telemetry_view_auth_sucesso_papeis_permitidos(
    papel: Role,
) -> None:
    """Validate that MEDICO, GESTOR_UNIDADE, and ADMIN_GLOBAL pass view auth."""
    user = _make_user(papel)
    authorized_user = await require_telemetry_view_auth(user)
    assert authorized_user == user


@pytest.mark.asyncio
async def test_require_telemetry_view_auth_sucesso_com_permissao_tma_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate that any user role possessing TMA_CONFIG passes view auth."""
    from src.core.authz import roles

    monkeypatch.setitem(
        roles.ROLE_PERMISSIONS,
        "AUDITOR_ESPECIAL",
        frozenset({Permission.TMA_CONFIG}),
    )
    user = _make_user(papel="AUDITOR_ESPECIAL")
    authorized_user = await require_telemetry_view_auth(user)
    assert authorized_user == user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "papel_proibido",
    [Role.PACIENTE, Role.FATURAMENTO],
)
async def test_require_telemetry_view_auth_proibido_ofensivo(
    papel_proibido: Role,
) -> None:
    """Validate ForbiddenError with offending value and expected shape."""
    user = _make_user(papel_proibido)
    with pytest.raises(ForbiddenError) as exc_info:
        await require_telemetry_view_auth(user)

    msg = str(exc_info.value)
    assert papel_proibido.value in msg
    assert "esperados" in msg
    assert "ADMIN_GLOBAL" in msg or "MEDICO" in msg


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "papel",
    [Role.GESTOR_UNIDADE, Role.ADMIN_GLOBAL],
)
async def test_require_telemetry_config_auth_sucesso_gestor_admin(
    papel: Role,
) -> None:
    """Validate that GESTOR_UNIDADE and ADMIN_GLOBAL pass config auth."""
    user = _make_user(papel)
    authorized_user = await require_telemetry_config_auth(user)
    assert authorized_user == user


@pytest.mark.asyncio
async def test_require_telemetry_config_auth_sucesso_com_permissao_tma_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate that any user possessing TMA_CONFIG passes config auth."""
    from src.core.authz import roles

    monkeypatch.setitem(
        roles.ROLE_PERMISSIONS,
        "GESTOR_DELEGADO",
        frozenset({Permission.TMA_CONFIG}),
    )
    user = _make_user(papel="GESTOR_DELEGADO")
    authorized_user = await require_telemetry_config_auth(user)
    assert authorized_user == user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "papel_proibido",
    [Role.MEDICO, Role.PACIENTE, Role.FATURAMENTO],
)
async def test_require_telemetry_config_auth_proibido_ofensivo(
    papel_proibido: Role,
) -> None:
    """Validate ForbiddenError on config auth for MEDICO, PACIENTE, FATURAMENTO."""
    user = _make_user(papel_proibido)
    with pytest.raises(ForbiddenError) as exc_info:
        await require_telemetry_config_auth(user)

    msg = str(exc_info.value)
    assert papel_proibido.value in msg
    assert "esperados" in msg
    assert "GESTOR_UNIDADE" in msg
