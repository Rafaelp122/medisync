"""Unit tests for JWT token issuance, decoding, and lifecycle validation."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from src.core.uuid7 import uuid7
from src.modules.auth.application.ports.token_service_port import TokenServicePort
from src.modules.auth.domain.exceptions import (
    TokenExpiradoError,
    TokenInvalidoError,
)
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService


def test_jwt_token_service_conformance() -> None:
    """Validate that JWTTokenService satisfies TokenServicePort."""
    service = JWTTokenService(secret_key="unit-test-secret-key-min-32-chars-long")
    assert isinstance(service, TokenServicePort)


def test_jwt_issue_and_validate_tokens() -> None:
    """Validate issuing and validating access and refresh tokens."""
    service = JWTTokenService(
        secret_key="unit-test-secret-key-min-32-chars-long",
        algorithm="HS256",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
    )
    user_id = uuid7()
    org_id = 42
    papel = "MEDICO"

    tokens = service.gerar_tokens(
        usuario_id=user_id,
        organizacao_id=org_id,
        papel=papel,
    )

    assert tokens.access_token is not None
    assert tokens.refresh_token is not None
    assert tokens.token_type == "bearer"
    assert tokens.expires_in == 900
    assert tokens.refresh_expires_in == 604800

    # Validate access token
    access_payload = service.validar_access_token(tokens.access_token)
    assert access_payload.sub == user_id
    assert access_payload.org_id == org_id
    assert access_payload.papel == papel
    assert access_payload.type == "access"
    assert access_payload.jti is not None

    # Validate refresh token
    refresh_payload = service.validar_refresh_token(tokens.refresh_token)
    assert refresh_payload.sub == user_id
    assert refresh_payload.org_id == org_id
    assert refresh_payload.papel == papel
    assert refresh_payload.type == "refresh"
    assert refresh_payload.jti is not None
    assert refresh_payload.jti != access_payload.jti


def test_jwt_type_mismatch_rejected() -> None:
    """Validate that access token cannot be used as refresh token and vice versa."""
    service = JWTTokenService(secret_key="unit-test-secret-key-min-32-chars-long")
    tokens = service.gerar_tokens(
        usuario_id=uuid7(),
        organizacao_id=1,
        papel="ADMIN_GLOBAL",
    )

    with pytest.raises(TokenInvalidoError) as exc_info1:
        service.validar_access_token(tokens.refresh_token)
    assert "esperado 'access'" in str(exc_info1.value)

    with pytest.raises(TokenInvalidoError) as exc_info2:
        service.validar_refresh_token(tokens.access_token)
    assert "esperado 'refresh'" in str(exc_info2.value)


def test_jwt_expired_token_rejected() -> None:
    """Validate that expired tokens raise TokenExpiradoError."""
    secret = "unit-test-secret-key-min-32-chars-long"
    service = JWTTokenService(secret_key=secret)
    past = datetime.now(UTC) - timedelta(minutes=5)
    expired_payload = {
        "sub": str(uuid7()),
        "org_id": 1,
        "papel": "MEDICO",
        "iat": int(past.timestamp()),
        "exp": int(past.timestamp()),
        "jti": str(uuid7()),
        "type": "access",
    }
    expired_token = jwt.encode(  # pyright: ignore[reportUnknownMemberType]
        expired_payload, secret, algorithm="HS256"
    )

    with pytest.raises(TokenExpiradoError):
        service.validar_access_token(expired_token)


def test_jwt_tampered_or_invalid_signature_rejected() -> None:
    """Validate that tampered signature or malformed token raises TokenInvalidoError."""
    service1 = JWTTokenService(secret_key="secret-key-one-min-32-chars-long")
    service2 = JWTTokenService(secret_key="secret-key-two-min-32-chars-long")

    tokens = service1.gerar_tokens(
        usuario_id=uuid7(),
        organizacao_id=1,
        papel="MEDICO",
    )

    # Validating with different secret key
    with pytest.raises(TokenInvalidoError):
        service2.validar_access_token(tokens.access_token)

    # Validating malformed token
    with pytest.raises(TokenInvalidoError):
        service1.validar_access_token("not-a-valid-jwt-token")
