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
    """Extrai e valida token Bearer assegurando isolamento multi-tenant (ADR-003).

    Verifica revogação em tempo real via Valkey e alinha tenant context (LGPD Art. 11).
    Decisões: docs/adrs/ADR-003-Multi-Tenancy-Logico-Postgres-RLS.md
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    if credentials is None:
        raise UnauthorizedError(
            f"Credencial de autenticação não fornecida (recebido: {credentials}). "
            "Envie o token no cabeçalho Authorization: Bearer <token>."
        )

    raw_token = credentials.credentials
    user = decode_access_token(raw_token)

    # Validate against Valkey token revocation / blacklist in real time
    if await is_token_revoked(user.token_id):
        raise TokenRevogadoError(
            f"Token de acesso revogado (jti={user.token_id}). Realize novo login."
        )

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
    """Garante autenticação válida do usuário solicitante (ADR-003).

    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    return current_user


def require_role(*roles: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Fabrica guard de autorização macro RBAC por papéis de usuário (ADR-003).

    Regras: docs/explanation/architecture/security-and-authorization.md
    """

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
    """Alias para require_role (ADR-003).

    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    return require_role(*roles)


def require_permission(
    *permissions: str,
) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Fabrica guard de autorização por permissões granulares de acesso (ADR-003).

    Regras: docs/explanation/architecture/security-and-authorization.md
    """

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
