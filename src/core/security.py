"""Security and cryptographic hashing utilities using Argon2id."""

from pwdlib import PasswordHash

# Initialize PasswordHash with recommended Argon2id configuration
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Generate an Argon2id cryptographic hash for the given plain text password."""
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify whether a plain text password matches an Argon2id hash."""
    if not hashed_password:
        return False
    try:
        return _password_hash.verify(password, hashed_password)
    except Exception:
        return False
