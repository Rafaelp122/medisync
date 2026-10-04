"""Multi-tier authorization framework (Tier 1 Macro RBAC and security context)."""

from src.core.authz.dependencies import (
    CurrentUserDep,
    get_current_user,
    require_authenticated_user,
    require_permission,
    require_role,
    require_roles,
)
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import ROLE_PERMISSIONS, Permission, Role
from src.core.authz.token import decode_access_token

__all__ = [
    "ROLE_PERMISSIONS",
    "AuthenticatedUser",
    "CurrentUserDep",
    "Permission",
    "Role",
    "decode_access_token",
    "get_current_user",
    "require_authenticated_user",
    "require_permission",
    "require_role",
    "require_roles",
]
