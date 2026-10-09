"""Port defining token revocation operations for distributed invalidation."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class TokenRevocationPort(Protocol):
    """Protocol for checking and registering revoked JWT token identifiers (JTI)."""

    async def revogar(self, jti: str, exp_segundos: int = 86400 * 7) -> None:
        """Mark token JTI as revoked until expiry."""
        ...

    async def is_revogado(self, jti: str) -> bool:
        """Check whether token JTI was revoked."""
        ...
