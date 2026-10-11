"""FastAPI security dependencies and authorization guards (Tier 1 Macro RBAC).

Conforms to OWASP Authorization Cheat Sheet (Least Privilege & Deny by Default).
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.authz.models import AuthenticatedUser
from src.core.authz.revocation import is_token_revoked
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.context import get_current_tenant_id, set_current_tenant_id
from src.core.errors import ForbiddenError, TokenRevogadoError, UnauthorizedError

http_bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Token de autenticação JWT Bearer",
)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> AuthenticatedUser:
    """Extract, decode, and validate the Bearer token from Authorization header.

    Also validates cross-tenant isolation and checks real-time revocation in Valkey.

    Raises:
        UnauthorizedError: If header is missing, malformed, or token is invalid/expired.
        TokenRevogadoError: If token JTI is listed in Valkey revocation store.
        ForbiddenError: If user tenant mismatches the requested tenant context.
    """
    if credentials is None:
        raise UnauthorizedError(
            "Credencial de autenticação não fornecida. "
            "Envie o token no cabeçalho Authorization: Bearer <token>."
        )

    raw_token = credentials.credentials
    user = decode_access_token(raw_token)

    # Validate against Valkey token revocation / blacklist in real time
    if await is_token_revoked(user.token_id):
        raise TokenRevogadoError("Token de acesso revogado. Realize novo login.")

    # Validate Tenant Isolation (defense in depth alongside PostgreSQL RLS)
    active_tenant = get_current_tenant_id()
    if active_tenant is None:
        set_current_tenant_id(user.organizacao_id)
    elif user.papel != Role.ADMIN_GLOBAL and user.organizacao_id != active_tenant:
        raise ForbiddenError(
            f"Acesso negado: o token pertence à organização {user.organizacao_id}, "
            f"mas o contexto solicitado é da organização {active_tenant}."
        )

    return user


CurrentUserDep = Annotated[AuthenticatedUser, Security(get_current_user)]


def require_authenticated_user(current_user: CurrentUserDep) -> AuthenticatedUser:
    """Ensure the request is authenticated with a valid token."""
    return current_user


def require_role(*roles: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Dependency factory restricting endpoint to users possessing one of the roles."""

    def role_checker(
        current_user: Annotated[
            AuthenticatedUser,
            Security(get_current_user, scopes=list(roles)),
        ],
    ) -> AuthenticatedUser:
        if not current_user.has_role(*roles):
            allowed_roles = ", ".join(roles)
            raise ForbiddenError(
                f"Acesso negado: o papel '{current_user.papel}' não possui "
                f"autorização para este recurso. Papéis permitidos: {allowed_roles}."
            )
        return current_user

    return role_checker


def require_roles(*roles: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Alias for require_role."""
    return require_role(*roles)


def require_permission(
    *permissions: str,
) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Dependency factory requiring user role to possess all specified permissions."""

    def permission_checker(
        current_user: Annotated[
            AuthenticatedUser,
            Security(get_current_user, scopes=list(permissions)),
        ],
    ) -> AuthenticatedUser:
        missing = [p for p in permissions if not current_user.has_permission(p)]
        if missing:
            missing_str = ", ".join(missing)
            raise ForbiddenError(
                f"Acesso negado: o papel '{current_user.papel}' não possui "
                f"as seguintes permissões necessárias: {missing_str}."
            )
        return current_user

    return permission_checker
