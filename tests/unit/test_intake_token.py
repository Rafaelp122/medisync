"""Unit tests for provisional intake token generation and verification."""

import time

import pytest
from src.core.security import create_intake_token, verify_intake_token
from src.core.uuid7 import uuid7

SECRET = "super-secret-key-for-testing-purposes-only-32-chars"


def test_create_and_verify_intake_token_happy_path() -> None:
    paciente_id = uuid7()
    org_id = 42

    token = create_intake_token(
        paciente_id=paciente_id,
        organizacao_id=org_id,
        secret_key=SECRET,
        expires_in_seconds=3600,
    )

    assert isinstance(token, str)
    assert "." in token

    payload = verify_intake_token(token=token, secret_key=SECRET)
    assert payload["paciente_id"] == str(paciente_id)
    assert payload["organizacao_id"] == org_id
    assert payload["tipo"] == "intake_provisional"
    assert payload["exp"] > time.time()


def test_verify_intake_token_tampered_payload_fails() -> None:
    paciente_id = uuid7()
    token = create_intake_token(
        paciente_id=paciente_id,
        organizacao_id=1,
        secret_key=SECRET,
    )

    parts = token.split(".")
    tampered_token = f"extra{parts[0]}.{parts[1]}"

    with pytest.raises(ValueError, match=r"inválid|adulterad"):
        verify_intake_token(token=tampered_token, secret_key=SECRET)


def test_verify_intake_token_wrong_secret_fails() -> None:
    paciente_id = uuid7()
    token = create_intake_token(
        paciente_id=paciente_id,
        organizacao_id=1,
        secret_key=SECRET,
    )

    with pytest.raises(ValueError, match=r"inválid|adulterad"):
        verify_intake_token(
            token=token, secret_key="wrong-secret-key-which-fails-signature"
        )


def test_verify_intake_token_expired_fails() -> None:
    paciente_id = uuid7()
    token = create_intake_token(
        paciente_id=paciente_id,
        organizacao_id=1,
        secret_key=SECRET,
        expires_in_seconds=-10,  # Already expired
    )

    with pytest.raises(ValueError, match="expirad"):
        verify_intake_token(token=token, secret_key=SECRET)
