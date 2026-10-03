"""Unit tests for Argon2id password hasher adapter."""

from src.modules.auth.application.ports.password_hasher_port import (
    PasswordHasherPort,
)
from src.modules.auth.infrastructure.argon2_hasher import (
    Argon2PasswordHasher,
)


def test_argon2_hasher_conformance() -> None:
    """Validate that Argon2PasswordHasher satisfies PasswordHasherPort."""
    hasher = Argon2PasswordHasher()
    assert isinstance(hasher, PasswordHasherPort)


def test_argon2_hash_and_verify() -> None:
    """Validate password hashing with Argon2id and constant-time verification."""
    hasher = Argon2PasswordHasher()
    password = "SuperSecretMedicalPassword123!"

    hashed = hasher.hash(password)
    assert hashed.startswith("$argon2id$")
    assert hasher.verify(password, hashed) is True
    assert hasher.verify("WrongPassword!", hashed) is False
    assert hasher.verify("", hashed) is False


def test_argon2_needs_rehash() -> None:
    """Validate needs_rehash identifies legacy or foreign hashes."""
    hasher = Argon2PasswordHasher()
    argon_hash = hasher.hash("test")
    assert hasher.needs_rehash(argon_hash) is False
    assert hasher.needs_rehash("$pbkdf2-sha256$oldhash") is True
    assert hasher.needs_rehash("plain_text") is True


def test_argon2_dummy_verify_runs_safely() -> None:
    """Validate dummy_verify executes without raising exceptions."""
    hasher = Argon2PasswordHasher()
    # Must execute smoothly to protect against timing attacks
    hasher.dummy_verify()
