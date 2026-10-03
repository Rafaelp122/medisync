import contextlib

from pwdlib import PasswordHash

from src.modules.auth.application.ports.password_hasher_port import (
    PasswordHasherPort,
)

_PASSWORD_HASH = PasswordHash.recommended()
_DUMMY_HASH: str = _PASSWORD_HASH.hash("dummy-constant-time-defense-pwd")


class Argon2PasswordHasher(PasswordHasherPort):
    """Secure password hasher using Argon2id per RFC 9106 and OWASP."""

    def __init__(self, hasher: PasswordHash | None = None) -> None:
        self._hasher = hasher or _PASSWORD_HASH

    def hash(self, password: str) -> str:
        """Generate Argon2id hash for the given plain password."""
        return self._hasher.hash(password)

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Verify plain password against stored hash in constant time."""
        try:
            return bool(self._hasher.verify(plain_password, hashed_password))
        except Exception:
            return False

    def needs_rehash(self, hashed_password: str) -> bool:
        """Check if stored hash needs upgrading."""
        return not hashed_password.startswith("$argon2id$")

    def dummy_verify(self) -> None:
        """Execute constant-time dummy verification to mitigate timing attacks."""
        with contextlib.suppress(Exception):
            self._hasher.verify("dummy-constant-time-defense-pwd", _DUMMY_HASH)
