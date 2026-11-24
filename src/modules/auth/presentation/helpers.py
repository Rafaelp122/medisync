"""Presentation helpers for authentication endpoints (ADR-009 pure)."""

from fastapi import Request, Response

AUTH_COOKIE_NAME = "refresh_token"
AUTH_COOKIE_PATH = "/api/v1/auth"
DEFAULT_REFRESH_COOKIE_MAX_AGE_DAYS = 7


def resolve_cookie_secure(
    request: Request | None = None,
    *,
    secure: bool | None = None,
    environment: str | None = None,
) -> bool:
    """Resolve dinamicamente se o cookie deve conter o atributo Secure.

    Regras: RN-AUT-08, OWASP ASVS v4.0 (V3.4.1), ADR-009.
    Documentação: docs/explanation/domains/auth-domain.md
    """
    if secure is not None:
        return secure
    if environment in ("production", "staging"):
        return True
    if request is not None:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        scheme = request.url.scheme or str(request.scope.get("scheme", ""))
        if scheme == "https" or forwarded_proto == "https":
            return True
    return False


def set_refresh_token_cookie(
    response: Response,
    refresh_token: str,
    *,
    request: Request | None = None,
    max_age_days: int = DEFAULT_REFRESH_COOKIE_MAX_AGE_DAYS,
    secure: bool | None = None,
) -> None:
    """Define cookie HttpOnly, SameSite=Strict para transporte seguro do refresh token.

    Regras: RN-AUT-05, RN-AUT-08, OWASP ASVS v4.0 (V3.4.1).
    Documentação: docs/explanation/domains/auth-domain.md
    """
    is_secure = resolve_cookie_secure(request, secure=secure)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age_days * 86400,
        path=AUTH_COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=is_secure,
    )


def clear_refresh_token_cookie(
    response: Response,
    *,
    request: Request | None = None,
    secure: bool | None = None,
) -> None:
    """Expurga cookie HttpOnly com max_age=0 para logout síncrono.

    Regras: RN-AUT-06, OWASP ASVS v4.0 (V3.4.1).
    Documentação: docs/explanation/domains/auth-domain.md
    """
    is_secure = resolve_cookie_secure(request, secure=secure)
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path=AUTH_COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=is_secure,
    )


def extract_refresh_token(
    request: Request,
    body_token: str | None = None,
) -> str | None:
    """Extrai refresh token suportando transporte por cookie HttpOnly e payload JSON.

    Prioriza payload explicito no corpo (clientes de API/scripts legados) e utiliza
    o cookie HttpOnly da requisicao quando o corpo for omitido (navegadores/SPA).
    Regras: RN-AUT-05, ADR-012.
    Documentação: docs/explanation/domains/auth-domain.md
    """
    if body_token and body_token.strip():
        return body_token.strip()
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie_token and cookie_token.strip():
        return cookie_token.strip()
    return None
