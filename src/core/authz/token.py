from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from src.core.authz.models import AuthenticatedUser
from src.core.config import get_settings
from src.core.errors import UnauthorizedError
from src.core.uuid7 import uuid7


def create_access_token(
    usuario_id: UUID,
    papel: str,
    secret_key: str | None = None,
    algorithm: str | None = None,
    expire_minutes: int | None = None,
) -> str:
    """Gera token JWT com claims de identidade e papel RBAC (ADR-013).

    Assegura vinculação criptográfica da identidade do ator (LGPD Art. 11).
    Decisões: docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    if secret_key is None or algorithm is None or expire_minutes is None:
        settings = get_settings()
        key = secret_key or settings.JWT_SECRET_KEY
        algo = algorithm or settings.JWT_ALGORITHM
        exp_minutes = (
            expire_minutes
            if expire_minutes is not None
            else settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    else:
        key = secret_key
        algo = algorithm
        exp_minutes = expire_minutes
    now = datetime.now(UTC)
    access_exp = now + timedelta(minutes=exp_minutes)

    payload: dict[str, Any] = {
        "sub": str(usuario_id),
        "papel": papel,
        "iat": int(now.timestamp()),
        "exp": int(access_exp.timestamp()),
        "jti": str(uuid7()),
        "type": "access",
    }
    return jwt.encode(  # pyright: ignore[reportUnknownMemberType]
        payload, key, algorithm=algo
    )


def decode_access_token(
    token: str,
    secret_key: str | None = None,
    algorithm: str | None = None,
    *,
    allowed_types: tuple[str, ...] = ("access",),
) -> AuthenticatedUser:
    """Decodifica e valida token JWT com verificação estrita de claims (ADR-013).

    Garante integridade criptográfica e papel do usuário (LGPD Art. 11).
    Decisões: docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    if secret_key is None or algorithm is None:
        settings = get_settings()
        key = secret_key or settings.JWT_SECRET_KEY
        algo = algorithm or settings.JWT_ALGORITHM
    else:
        key = secret_key
        algo = algorithm

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[algo],
            options={
                "require": ["sub", "papel", "exp", "jti", "type"],
                "verify_exp": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError(
            f"Token de acesso expirado ({exc}). Realize novo login."
        ) from exc
    except jwt.InvalidTokenError as exc:
        preview = f"{token[:12]}..." if len(token) > 12 else token
        raise UnauthorizedError(
            f"Token de acesso inválido ou malformado ('{preview}'): {exc}."
        ) from exc

    token_type = payload.get("type")
    if not isinstance(token_type, str) or token_type not in allowed_types:
        expected_desc = (
            "token de acesso ('access')."
            if allowed_types == ("access",)
            else f"um dos tipos: {sorted(allowed_types)}."
        )
        raise UnauthorizedError(
            f"Tipo de token '{token_type}' inválido. Esperado {expected_desc}"
        )

    try:
        usuario_id = UUID(str(payload["sub"]))
        papel = str(payload["papel"])
        token_id = UUID(str(payload["jti"]))
    except (ValueError, KeyError, TypeError) as exc:
        err_type = type(exc).__name__
        raise UnauthorizedError(
            f"Claims do token de acesso inválidas ({err_type}: {exc})."
        ) from exc

    return AuthenticatedUser(
        usuario_id=usuario_id,
        papel=papel,
        token_id=token_id,
        raw_token=token,
        token_type=token_type,
    )
