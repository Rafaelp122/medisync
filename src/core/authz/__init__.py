"""Multi-tier authorization framework (Tier 1 Macro RBAC and security context)."""

from src.core.authz.dependencies import (
    BearerAuthSettings,
    BearerAuthSettingsDep,
    CurrentUserDep,
    OptionalBearerAuthSettingsDep,
    OptionalTokenRevocationDep,
    get_bearer_auth_settings,
    get_current_user,
    http_bearer_scheme,
    require_permission,
    require_role,
    resolve_bearer_principal,
)
from src.core.authz.models import AuthenticatedUser, BearerPrincipal
from src.core.authz.revocation import (
    MemoryTokenRevocation,
    TokenRevocationDep,
    TokenRevocationPort,
    ValkeyTokenRevocation,
    get_token_revocation,
)
from src.core.authz.roles import ROLE_PERMISSIONS, Permission, Role
from src.core.authz.token import decode_access_token

__all__ = [
    "ROLE_PERMISSIONS",
    "AuthenticatedUser",
    "BearerAuthSettings",
    "BearerAuthSettingsDep",
    "BearerPrincipal",
    "CurrentUserDep",
    "MemoryTokenRevocation",
    "OptionalBearerAuthSettingsDep",
    "OptionalTokenRevocationDep",
    "Permission",
    "Role",
    "TokenRevocationDep",
    "TokenRevocationPort",
    "ValkeyTokenRevocation",
    "decode_access_token",
    "get_bearer_auth_settings",
    "get_current_user",
    "get_token_revocation",
    "http_bearer_scheme",
    "require_permission",
    "require_role",
    "resolve_bearer_principal",
]
