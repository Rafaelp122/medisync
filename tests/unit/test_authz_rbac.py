"""Unit tests for Tier 1 Macro RBAC roles, permissions, token decoder, and guards."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from src.core.authz.dependencies import (
    get_current_user,
    require_permission,
    require_role,
)
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import ROLE_PERMISSIONS, Permission, Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.context import set_current_tenant_id
from src.core.errors import ForbiddenError, UnauthorizedError


def _create_token(
    usuario_id: UUID,
    organizacao_id: int,
    papel: str,
    secret_key: str,
    expires_in_seconds: int = 900,
    token_type: str = "access",  # noqa: S107
    jti: UUID | None = None,
) -> str:
    """Helper to generate JWT tokens for unit testing."""
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=expires_in_seconds)
    payload = {
        "sub": str(usuario_id),
        "org_id": organizacao_id,
        "papel": papel,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(jti or uuid4()),
        "type": token_type,
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def test_role_and_permission_matrix() -> None:
    """Validate OWASP least privilege and CFM compliance in role-permission matrix."""
    # 1. Medico has clinical and queue permissions
    medico_perms = ROLE_PERMISSIONS[Role.MEDICO]
    assert Permission.PRONTUARIO_VIEW in medico_perms
    assert Permission.PRONTUARIO_EDIT in medico_perms
    assert Permission.DOC_SIGN in medico_perms
    assert Permission.QUEUE_CALL in medico_perms
    assert Permission.QUEUE_VIEW in medico_perms
    assert Permission.BILLING_CONSOLIDATE not in medico_perms

    # 2. Gestor and Admin CANNOT view medical records (CFM 1.821/2007 rule)
    admin_perms = ROLE_PERMISSIONS[Role.ADMIN_GLOBAL]
    assert Permission.PRONTUARIO_VIEW not in admin_perms
    assert Permission.PRONTUARIO_EDIT not in admin_perms
    assert Permission.DOC_SIGN not in admin_perms
    assert Permission.TMA_CONFIG in admin_perms
    assert Permission.PROFISSIONAL_MANAGE in admin_perms

    gestor_perms = ROLE_PERMISSIONS[Role.GESTOR_UNIDADE]
    assert Permission.PRONTUARIO_VIEW not in gestor_perms
    assert Permission.TMA_CONFIG in gestor_perms

    # 3. Faturamento only consolidates billing
    fat_perms = ROLE_PERMISSIONS[Role.FATURAMENTO]
    assert fat_perms == frozenset({Permission.BILLING_CONSOLIDATE})

    # 4. Paciente can only track their own queue position and documents
    pac_perms = ROLE_PERMISSIONS[Role.PACIENTE]
    assert pac_perms == frozenset(
        {Permission.PATIENT_QUEUE_TRACK, Permission.PATIENT_DOC_VIEW}
    )


def test_authenticated_user_methods() -> None:
    """Validate has_role and has_permission helper methods on AuthenticatedUser."""
    user = AuthenticatedUser(
        usuario_id=uuid4(),
        organizacao_id=1,
        papel=Role.MEDICO,
        token_id=uuid4(),
        raw_token="fake-token",
    )
    assert user.has_role(Role.MEDICO) is True
    assert user.has_role(Role.MEDICO, Role.ADMIN_GLOBAL) is True
    assert user.has_role(Role.FATURAMENTO) is False
    assert user.has_permission(Permission.PRONTUARIO_VIEW) is True
    assert user.has_permission(Permission.BILLING_CONSOLIDATE) is False


def test_decode_valid_access_token() -> None:
    """Verify successful decoding of standard valid JWT access token."""
    settings = get_settings()
    user_id = uuid4()
    token = _create_token(
        usuario_id=user_id,
        organizacao_id=42,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
    )

    user = decode_access_token(token)
    assert user.usuario_id == user_id
    assert user.organizacao_id == 42
    assert user.papel == Role.MEDICO
    assert user.raw_token == token


def test_decode_rejects_expired_token() -> None:
    """Verify expired token is rejected with UnauthorizedError."""
    settings = get_settings()
    token = _create_token(
        usuario_id=uuid4(),
        organizacao_id=42,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
        expires_in_seconds=-60,
    )
    with pytest.raises(UnauthorizedError, match="expirado"):
        decode_access_token(token)


def test_decode_rejects_tampered_token() -> None:
    """Verify invalid signature or corrupt token raises UnauthorizedError."""
    with pytest.raises(UnauthorizedError, match="inválido"):
        decode_access_token("corrupted.jwt.token")


def test_decode_rejects_refresh_token_for_api_access() -> None:
    """Verify that refresh token cannot be used directly as an access token."""
    settings = get_settings()
    token = _create_token(
        usuario_id=uuid4(),
        organizacao_id=42,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
        token_type="refresh",
    )
    with pytest.raises(UnauthorizedError, match="Esperado token de acesso"):
        decode_access_token(token)


def test_require_role_guard() -> None:
    """Verify require_role allows authorized roles and denies unauthorized ones."""
    medico_user = AuthenticatedUser(
        usuario_id=uuid4(),
        organizacao_id=1,
        papel=Role.MEDICO,
        token_id=uuid4(),
        raw_token="fake",
    )
    gestor_user = AuthenticatedUser(
        usuario_id=uuid4(),
        organizacao_id=1,
        papel=Role.GESTOR_UNIDADE,
        token_id=uuid4(),
        raw_token="fake",
    )

    medico_guard = require_role(Role.MEDICO)
    # Medico passes
    assert medico_guard(medico_user) == medico_user

    # Gestor is rejected with 403 Forbidden
    with pytest.raises(ForbiddenError) as exc_info:
        medico_guard(gestor_user)
    assert exc_info.value.status_code == 403
    assert "GESTOR_UNIDADE" in str(exc_info.value)


def test_require_permission_guard() -> None:
    """Verify require_permission dependency checks fine-grained permissions."""
    medico_user = AuthenticatedUser(
        usuario_id=uuid4(),
        organizacao_id=1,
        papel=Role.MEDICO,
        token_id=uuid4(),
        raw_token="fake",
    )

    view_guard = require_permission(Permission.PRONTUARIO_VIEW)
    assert view_guard(medico_user) == medico_user

    billing_guard = require_permission(Permission.BILLING_CONSOLIDATE)
    with pytest.raises(ForbiddenError) as exc_info:
        billing_guard(medico_user)
    assert exc_info.value.status_code == 403
    assert "billing:consolidate" in str(exc_info.value)


def test_get_current_user_tenant_mismatch() -> None:
    """Verify get_current_user enforces tenant isolation against active tenant."""
    settings = get_settings()
    token = _create_token(
        usuario_id=uuid4(),
        organizacao_id=10,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
    )

    # When context tenant is 20, non-admin user from tenant 10 is blocked with 403
    set_current_tenant_id(20)
    try:
        with pytest.raises(ForbiddenError, match="organização 10"):
            get_current_user(f"Bearer {token}")
    finally:
        set_current_tenant_id(None)


def test_get_current_user_missing_header() -> None:
    """Verify get_current_user raises 401 when Authorization header is absent."""
    with pytest.raises(UnauthorizedError, match="não fornecida"):
        get_current_user(None)
    with pytest.raises(UnauthorizedError, match="inválido"):
        get_current_user("Basic dXNlcjpwYXNz")
