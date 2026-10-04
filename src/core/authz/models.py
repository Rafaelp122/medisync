"""Domain model representing an authenticated user within security context."""

from dataclasses import dataclass
from uuid import UUID

from src.core.authz.roles import ROLE_PERMISSIONS


@dataclass(frozen=True)
class AuthenticatedUser:
    """Security principal extracted from validated JWT access token."""

    usuario_id: UUID
    organizacao_id: int
    papel: str
    token_id: UUID
    raw_token: str

    def has_role(self, *roles: str) -> bool:
        """Verify whether the user holds one of the specified roles."""
        return self.papel in roles

    def has_permission(self, permission: str) -> bool:
        """Verify whether user role grants the specified fine-grained permission."""
        allowed = ROLE_PERMISSIONS.get(self.papel, frozenset())
        return permission in allowed
