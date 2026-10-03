"""Port interface for Argon2id password hashing and constant-time verification."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class PasswordHasherPort(Protocol):
    """Port for hashing and verifying passwords adhering to OWASP & RFC 9106."""

    def hash(self, password: str) -> str:
        """Generate a secure Argon2id hash for the given plain password."""
        ...

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verify plain password against stored hash in constant time."""
        ...

    def needs_rehash(self, hashed_password: str) -> bool:
        """Check if stored hash needs re-hashing due to upgraded parameters."""
        ...

    def dummy_verify(self) -> None:
        """Execute constant-time dummy verification to mitigate timing attacks."""
        ...
