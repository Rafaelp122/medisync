"""Unit tests for Tier 1 Macro RBAC roles, permissions, token decoder, and guards."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
import src.core.authz as authz_pkg
import src.core.authz.dependencies as authz_deps
from fastapi import WebSocketException
from fastapi.security import HTTPAuthorizationCredentials
from src.core.authz.dependencies import (
    get_current_user,
    require_permission,
    require_role,
    resolve_bearer_principal,
)
from src.core.authz.models import AuthenticatedUser, BearerPrincipal
from src.core.authz.revocation import MemoryTokenRevocation, TokenRevocationPort
from src.core.authz.roles import (
    ROLE_PERMISSIONS,
    ROLES_REQUIRING_MFA,
    Permission,
    Role,
)
from src.core.authz.token import create_access_token, decode_access_token
from src.core.config import get_settings
from src.core.errors import (
    ForbiddenError,
    ServiceUnavailableError,
    TokenRevogadoError,
    UnauthorizedError,
)
from src.core.security import create_intake_token


def create_test_token(
    usuario_id: UUID,
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
        "papel": papel,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(jti or uuid4()),
        "type": token_type,
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


_create_token = create_test_token


def test_role_and_permission_matrix() -> None:
    """Validate simplified 4-role OWASP least privilege and CFM compliance."""
    assert set(Role) == {
        Role.GESTOR_UNIDADE,
        Role.MEDICO,
        Role.FATURAMENTO,
        Role.PACIENTE,
    }
    assert "ADMIN_GLOBAL" not in ROLE_PERMISSIONS
    assert frozenset({"MEDICO", "GESTOR_UNIDADE"}) == ROLES_REQUIRING_MFA

    # 1. Medico has clinical and queue permissions
    medico_perms = ROLE_PERMISSIONS[Role.MEDICO]
    assert Permission.PRONTUARIO_VIEW in medico_perms
    assert Permission.PRONTUARIO_EDIT in medico_perms
    assert Permission.DOC_SIGN in medico_perms
    assert Permission.QUEUE_CALL in medico_perms
    assert Permission.QUEUE_VIEW in medico_perms
    assert Permission.AMBULATORY_CONSOLIDATE not in medico_perms

    # 2. Gestor CANNOT view medical records (CFM 1.821/2007 rule)
    gestor_perms = ROLE_PERMISSIONS[Role.GESTOR_UNIDADE]
    assert Permission.PRONTUARIO_VIEW not in gestor_perms
    assert Permission.PRONTUARIO_EDIT not in gestor_perms
    assert Permission.DOC_SIGN not in gestor_perms
    assert Permission.TMA_CONFIG in gestor_perms
    assert Permission.PROFISSIONAL_MANAGE in gestor_perms

    # 3. Faturamento only consolidates ambulatory production
    fat_perms = ROLE_PERMISSIONS[Role.FATURAMENTO]
    assert fat_perms == frozenset({Permission.AMBULATORY_CONSOLIDATE})

    # 4. Paciente can only track their own queue position and documents
    pac_perms = ROLE_PERMISSIONS[Role.PACIENTE]
    assert pac_perms == frozenset(
        {Permission.PATIENT_QUEUE_TRACK, Permission.PATIENT_DOC_VIEW}
    )


def test_authenticated_user_methods() -> None:
    """Validate has_role and has_permission helper methods on AuthenticatedUser."""
    user = AuthenticatedUser(
        usuario_id=uuid4(),
        papel=Role.MEDICO,
        token_id=uuid4(),
        raw_token="fake-token",
    )
    assert not hasattr(user, "organizacao_id")
    assert user.has_role(Role.MEDICO) is True
    assert user.has_role(Role.MEDICO, Role.GESTOR_UNIDADE) is True
    assert user.has_role(Role.FATURAMENTO) is False
    assert user.has_permission(Permission.PRONTUARIO_VIEW) is True
    assert user.has_permission(Permission.AMBULATORY_CONSOLIDATE) is False


def test_create_and_decode_valid_access_token_without_org_claim() -> None:
    """Verify JWT creation and decoding operate without org_id claim."""
    settings = get_settings()
    user_id = uuid4()
    token = create_access_token(
        usuario_id=user_id,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
    )
    raw_claims = jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    assert "org_id" not in raw_claims

    user = decode_access_token(token)
    assert user.usuario_id == user_id
    assert user.papel == Role.MEDICO
    assert user.raw_token == token


def test_decode_rejects_expired_token() -> None:
    """Verify expired token is rejected with UnauthorizedError."""
    settings = get_settings()
    token = _create_token(
        usuario_id=uuid4(),
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
        papel=Role.MEDICO,
        token_id=uuid4(),
        raw_token="fake",
    )
    gestor_user = AuthenticatedUser(
        usuario_id=uuid4(),
        papel=Role.GESTOR_UNIDADE,
        token_id=uuid4(),
        raw_token="fake",
    )

    medico_guard = require_role(Role.MEDICO)
    assert medico_guard(medico_user) == medico_user

    with pytest.raises(ForbiddenError) as exc_info:
        medico_guard(gestor_user)
    assert exc_info.value.status_code == 403
    assert "GESTOR_UNIDADE" in str(exc_info.value)


def test_require_permission_guard() -> None:
    """Verify require_permission dependency checks fine-grained permissions."""
    medico_user = AuthenticatedUser(
        usuario_id=uuid4(),
        papel=Role.MEDICO,
        token_id=uuid4(),
        raw_token="fake",
    )

    view_guard = require_permission(Permission.PRONTUARIO_VIEW)
    assert view_guard(medico_user) == medico_user

    ambulatory_guard = require_permission(Permission.AMBULATORY_CONSOLIDATE)
    with pytest.raises(ForbiddenError) as exc_info:
        ambulatory_guard(medico_user)
    assert exc_info.value.status_code == 403
    assert "ambulatory:consolidate" in str(exc_info.value)


class FailingTokenRevocation(TokenRevocationPort):
    """Named fake simulating Valkey unavailability (fail-closed 503)."""

    async def revogar(self, jti: str, exp_segundos: int = 86400 * 7) -> None:
        raise ServiceUnavailableError(f"Valkey indisponível ao revogar '{jti}'.")

    async def marcar_revogado_se_nao_revogado(
        self, jti: str, exp_segundos: int = 86400 * 7
    ) -> bool:
        raise ServiceUnavailableError(f"Valkey indisponível ao revogar '{jti}'.")

    async def is_revogado(self, jti: str) -> bool:
        raise ServiceUnavailableError(f"Valkey indisponível ao consultar '{jti}'.")


@pytest.mark.asyncio
async def test_get_current_user_valid_token_without_tenant_context() -> None:
    """Verify get_current_user authenticates cleanly with MemoryTokenRevocation."""
    revocation = MemoryTokenRevocation()
    settings = get_settings()
    user_id = uuid4()
    token = _create_token(
        usuario_id=user_id,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
    )

    user = await get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
        revocation=revocation,
    )
    assert user.usuario_id == user_id
    assert user.papel == Role.MEDICO


@pytest.mark.asyncio
async def test_get_current_user_missing_header() -> None:
    """Verify get_current_user raises 401 when Authorization header is absent."""
    with pytest.raises(UnauthorizedError, match="não fornecida"):
        await get_current_user(None, revocation=MemoryTokenRevocation())


@pytest.mark.asyncio
async def test_get_current_user_revoked_token_raises_401() -> None:
    """Verify get_current_user raises TokenRevogadoError (401) when revoked."""
    revocation = MemoryTokenRevocation()
    jti = uuid4()
    await revocation.revogar(str(jti))

    settings = get_settings()
    token = _create_token(
        usuario_id=uuid4(),
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
        jti=jti,
    )

    with pytest.raises(TokenRevogadoError) as exc_info:
        await get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            revocation=revocation,
        )
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "TOKEN_REVOGADO"


@pytest.mark.asyncio
async def test_resolve_bearer_principal_supports_intake_and_jwt_http() -> None:
    """resolve_bearer_principal normalizes 2-part HMAC intake and 3-part JWT."""
    settings = get_settings()
    revocation = MemoryTokenRevocation()
    paciente_id = uuid4()
    intake_token = create_intake_token(paciente_id, settings.SECRET_KEY)

    intake_principal = await resolve_bearer_principal(
        intake_token,
        allowed_roles=(Role.PACIENTE,),
        accept_intake=True,
        revocation=revocation,
        secret_key=settings.SECRET_KEY,
        jwt_secret=settings.JWT_SECRET_KEY,
        jwt_algorithm=settings.JWT_ALGORITHM,
        transport="http",
    )
    assert isinstance(intake_principal, BearerPrincipal)
    assert intake_principal.actor_id == paciente_id
    assert intake_principal.papel == Role.PACIENTE.value
    assert intake_principal.auth_kind == "intake_hmac"
    assert intake_principal.token_id is None

    # Intake rejected when accept_intake=False
    with pytest.raises(UnauthorizedError, match="formato inválido"):
        await resolve_bearer_principal(
            intake_token,
            allowed_roles=(Role.PACIENTE,),
            accept_intake=False,
            revocation=revocation,
            secret_key=settings.SECRET_KEY,
            jwt_secret=settings.JWT_SECRET_KEY,
            jwt_algorithm=settings.JWT_ALGORITHM,
            transport="http",
        )

    # Valid JWT
    jti = uuid4()
    medico_id = uuid4()
    jwt_token = _create_token(
        usuario_id=medico_id,
        papel=Role.MEDICO.value,
        secret_key=settings.JWT_SECRET_KEY,
        jti=jti,
    )
    jwt_principal = await resolve_bearer_principal(
        jwt_token,
        allowed_roles=(Role.MEDICO,),
        accept_intake=False,
        revocation=revocation,
        secret_key=settings.SECRET_KEY,
        jwt_secret=settings.JWT_SECRET_KEY,
        jwt_algorithm=settings.JWT_ALGORITHM,
        transport="http",
    )
    assert jwt_principal.actor_id == medico_id
    assert jwt_principal.papel == Role.MEDICO.value
    assert jwt_principal.auth_kind == "jwt"
    assert jwt_principal.token_id == jti


@pytest.mark.asyncio
async def test_resolve_bearer_principal_maps_http_and_ws_errors() -> None:
    """resolve_bearer_principal maps 401->4401, 403->4403, and 503->1013 for WS."""
    settings = get_settings()
    revocation = MemoryTokenRevocation()
    jti = uuid4()
    token_pac = _create_token(
        usuario_id=uuid4(),
        papel=Role.PACIENTE.value,
        secret_key=settings.JWT_SECRET_KEY,
        jti=jti,
    )

    # HTTP 403 & WS 4403 for role mismatch
    with pytest.raises(ForbiddenError):
        await resolve_bearer_principal(
            token_pac,
            allowed_roles=(Role.MEDICO,),
            revocation=revocation,
            secret_key=settings.SECRET_KEY,
            jwt_secret=settings.JWT_SECRET_KEY,
            transport="http",
        )
    with pytest.raises(WebSocketException) as ws_forbidden:
        await resolve_bearer_principal(
            token_pac,
            allowed_roles=(Role.MEDICO,),
            revocation=revocation,
            secret_key=settings.SECRET_KEY,
            jwt_secret=settings.JWT_SECRET_KEY,
            transport="ws",
        )
    assert ws_forbidden.value.code == 4403

    # HTTP 401 & WS 4401 for revoked token
    await revocation.revogar(str(jti))
    with pytest.raises(TokenRevogadoError):
        await resolve_bearer_principal(
            token_pac,
            allowed_roles=(Role.PACIENTE,),
            revocation=revocation,
            secret_key=settings.SECRET_KEY,
            jwt_secret=settings.JWT_SECRET_KEY,
            transport="http",
        )
    with pytest.raises(WebSocketException) as ws_revoked:
        await resolve_bearer_principal(
            token_pac,
            allowed_roles=(Role.PACIENTE,),
            revocation=revocation,
            secret_key=settings.SECRET_KEY,
            jwt_secret=settings.JWT_SECRET_KEY,
            transport="ws",
        )
    assert ws_revoked.value.code == 4401

    # HTTP 503 & WS 1013 when revocation backend fails (fail-closed)
    fresh_token = _create_token(
        usuario_id=uuid4(),
        papel=Role.MEDICO.value,
        secret_key=settings.JWT_SECRET_KEY,
    )
    with pytest.raises(ServiceUnavailableError):
        await resolve_bearer_principal(
            fresh_token,
            allowed_roles=(Role.MEDICO,),
            revocation=FailingTokenRevocation(),
            secret_key=settings.SECRET_KEY,
            jwt_secret=settings.JWT_SECRET_KEY,
            transport="http",
        )
    with pytest.raises(WebSocketException) as ws_unavail:
        await resolve_bearer_principal(
            fresh_token,
            allowed_roles=(Role.MEDICO,),
            revocation=FailingTokenRevocation(),
            secret_key=settings.SECRET_KEY,
            jwt_secret=settings.JWT_SECRET_KEY,
            transport="ws",
        )
    assert ws_unavail.value.code == 1013


def test_orphan_authz_symbols_removed() -> None:
    """Orphan guards require_authenticated_user and require_roles must be absent."""
    assert not hasattr(authz_pkg, "require_authenticated_user")
    assert not hasattr(authz_pkg, "require_roles")
    assert not hasattr(authz_deps, "require_authenticated_user")
    assert not hasattr(authz_deps, "require_roles")
