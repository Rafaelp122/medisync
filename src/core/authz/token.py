"""JWT token decoding and verification for authorization guards."""

from typing import Any
from uuid import UUID

import jwt

from src.core.authz.models import AuthenticatedUser
from src.core.config import get_settings
from src.core.errors import UnauthorizedError


def decode_access_token(
    token: str,
    secret_key: str | None = None,
    algorithm: str | None = None,
) -> AuthenticatedUser:
    """Decode and validate a JWT access token into an AuthenticatedUser principal.

    Raises:
        UnauthorizedError: If the token is expired, tampered, invalid,
            or is a refresh token.
    """
    settings = get_settings()
    key = secret_key or settings.JWT_SECRET_KEY
    algo = algorithm or settings.JWT_ALGORITHM

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[algo],
            options={
                "require": ["sub", "org_id", "papel", "exp", "jti", "type"],
                "verify_exp": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token de acesso expirado.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Token de acesso inválido ou malformado.") from exc

    token_type = payload.get("type")
    if token_type != "access":  # noqa: S105
        raise UnauthorizedError(
            "Tipo de token inválido para autorização. Esperado token de acesso."
        )

    try:
        usuario_id = UUID(str(payload["sub"]))
        organizacao_id = int(payload["org_id"])
        papel = str(payload["papel"])
        token_id = UUID(str(payload["jti"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise UnauthorizedError("Claims do token de acesso malformadas.") from exc

    return AuthenticatedUser(
        usuario_id=usuario_id,
        organizacao_id=organizacao_id,
        papel=papel,
        token_id=token_id,
        raw_token=token,
    )
