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
    organizacao_id: int,
    papel: str,
    secret_key: str | None = None,
    algorithm: str | None = None,
    expire_minutes: int | None = None,
) -> str:
    """Gera token JWT com claims de autorização e tenant isolation (ADR-003).

    Assegura vinculação criptográfica do usuário ao tenant (LGPD Art. 11).
    Decisões: docs/adrs/ADR-003-Multi-Tenancy-Logico-Postgres-RLS.md
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    settings = get_settings()
    key = secret_key or settings.JWT_SECRET_KEY
    algo = algorithm or settings.JWT_ALGORITHM
    exp_minutes = (
        expire_minutes
        if expire_minutes is not None
        else settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    now = datetime.now(UTC)
    access_exp = now + timedelta(minutes=exp_minutes)

    payload: dict[str, Any] = {
        "sub": str(usuario_id),
        "org_id": organizacao_id,
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
) -> AuthenticatedUser:
    """Decodifica e valida token JWT com verificação estrita de claims (ADR-003).

    Garante integridade criptográfica e tenant principal (LGPD Art. 11).
    Decisões: docs/adrs/ADR-003-Multi-Tenancy-Logico-Postgres-RLS.md
    Regras: docs/explanation/architecture/security-and-authorization.md
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
        raise UnauthorizedError(
            f"Token de acesso expirado ({exc}). Realize novo login."
        ) from exc
    except jwt.InvalidTokenError as exc:
        preview = f"{token[:12]}..." if len(token) > 12 else token
        raise UnauthorizedError(
            f"Token de acesso inválido ou malformado ('{preview}'): {exc}."
        ) from exc

    token_type = payload.get("type")
    if token_type != "access":  # noqa: S105
        raise UnauthorizedError(
            f"Tipo de token '{token_type}' inválido. "
            "Esperado token de acesso ('access')."
        )

    try:
        usuario_id = UUID(str(payload["sub"]))
        organizacao_id = int(payload["org_id"])
        papel = str(payload["papel"])
        token_id = UUID(str(payload["jti"]))
    except (ValueError, KeyError, TypeError) as exc:
        err_type = type(exc).__name__
        raise UnauthorizedError(
            f"Claims do token de acesso inválidas ({err_type}: {exc})."
        ) from exc

    return AuthenticatedUser(
        usuario_id=usuario_id,
        organizacao_id=organizacao_id,
        papel=papel,
        token_id=token_id,
        raw_token=token,
    )
