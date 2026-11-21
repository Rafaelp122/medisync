"""Domain models representing authenticated security principals."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from src.core.authz.roles import ROLE_PERMISSIONS


@dataclass(frozen=True)
class AuthenticatedUser:
    """Security principal extracted from validated JWT access token."""

    usuario_id: UUID
    papel: str
    token_id: UUID
    raw_token: str
    token_type: str = "access"  # noqa: S105

    def has_role(self, *roles: str) -> bool:
        """Verify whether the user holds one of the specified roles."""
        return self.papel in roles

    def has_permission(self, permission: str) -> bool:
        """Verify whether user role grants the specified fine-grained permission."""
        allowed = ROLE_PERMISSIONS.get(self.papel, frozenset())
        return permission in allowed


@dataclass(frozen=True)
class BearerPrincipal:
    """Normalized principal extracted from hybrid JWT or provisional intake HMAC."""

    actor_id: UUID
    papel: str
    auth_kind: Literal["jwt", "intake_hmac"]
    token_id: UUID | None = None
    raw_token: str = ""
    token_type: str = "access"  # noqa: S105
    is_intake_restrito: bool = False
