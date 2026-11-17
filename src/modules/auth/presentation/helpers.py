"""Presentation helpers for authentication endpoints."""

from fastapi import Request, Response

from src.core.config import get_settings
from src.core.errors import ValidationError

AUTH_COOKIE_NAME = "refresh_token"
AUTH_COOKIE_PATH = "/api/v1/auth"
DEFAULT_REFRESH_COOKIE_MAX_AGE_DAYS = 7


def resolve_login_tenant_id(
    body_org_id: int | None,
    context_tenant_id: int | None,
    *,
    multi_tenancy_enabled: bool | None = None,
    default_tenant_id: int | None = None,
) -> int:
    """Resolve organização no login respeitando modo single-tenant (anti-spoofing).

    Regras: RN-AUT-01, ADR-001, ADR-003.
    Documentação: docs/explanation/domains/auth-domain.md
    """
    settings = get_settings()
    is_multi = (
        settings.MULTI_TENANCY_ENABLED
        if multi_tenancy_enabled is None
        else multi_tenancy_enabled
    )
    if not is_multi:
        resolved = (
            default_tenant_id
            if default_tenant_id is not None
            else settings.DEFAULT_TENANT_ID
        )
        if resolved is not None and resolved > 0:
            return resolved
        raise ValidationError(
            f"Tenant padrão '{resolved!r}' inválido no modo single-tenant; "
            "esperado DEFAULT_TENANT_ID inteiro positivo (> 0)."
        )
    if body_org_id is not None:
        if body_org_id <= 0:
            raise ValidationError(
                f"Identificador da organização (tenant) '{body_org_id}' inválido; "
                "esperado valor inteiro positivo (> 0)."
            )
        return body_org_id
    if context_tenant_id is not None and context_tenant_id > 0:
        return context_tenant_id
    raise ValidationError(
        "Identificador da organização (tenant) inválido ou não informado "
        f"(recebido body_org_id={body_org_id!r}, "
        f"context_tenant_id={context_tenant_id!r}; esperado inteiro positivo > 0 "
        "no corpo ou no cabeçalho X-Tenant-ID)."
    )


def resolve_cookie_secure(
    request: Request | None = None, *, secure: bool | None = None
) -> bool:
    """Resolve dinamicamente se o cookie deve conter o atributo Secure.

    Regras: RN-AUT-08, OWASP ASVS v4.0 (V3.4.1).
    Documentação: docs/explanation/domains/auth-domain.md
    """
    if secure is not None:
        return secure
    settings = get_settings()
    if settings.ENVIRONMENT in ("production", "staging"):
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
