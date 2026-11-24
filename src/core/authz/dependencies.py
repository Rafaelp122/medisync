"""FastAPI security dependencies and unified Bearer principal resolver.

Conforms to OWASP Authorization Cheat Sheet (Least Privilege & Deny by Default).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, NoReturn
from uuid import UUID

from fastapi import Depends, Security, WebSocketException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.authz.models import AuthenticatedUser, BearerPrincipal
from src.core.authz.revocation import (
    TokenRevocationPort,
    get_token_revocation,
)
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.errors import (
    DomainError,
    ForbiddenError,
    TokenRevogadoError,
    UnauthorizedError,
)
from src.core.security import verify_intake_token

http_bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Token de autenticação JWT Bearer",
)


@dataclass(frozen=True)
class BearerAuthSettings:
    """Resolved cryptographic settings injected into presentation authz guards."""

    secret_key: str
    jwt_secret: str
    jwt_algorithm: str


def get_bearer_auth_settings() -> BearerAuthSettings:
    """Resolve cryptographic verification secrets from active application settings."""
    settings = get_settings()
    return BearerAuthSettings(
        secret_key=settings.SECRET_KEY,
        jwt_secret=settings.JWT_SECRET_KEY,
        jwt_algorithm=settings.JWT_ALGORITHM,
    )


BearerAuthSettingsDep = Annotated[BearerAuthSettings, Depends(get_bearer_auth_settings)]
OptionalBearerAuthSettingsDep = Annotated[
    BearerAuthSettings | None, Depends(get_bearer_auth_settings)
]
OptionalTokenRevocationDep = Annotated[
    TokenRevocationPort | None, Depends(get_token_revocation)
]


def _raise_transport_error(
    exc: DomainError, transport: Literal["http", "ws"]
) -> NoReturn:
    if transport == "http":
        raise exc
    if isinstance(exc, ForbiddenError):
        raise WebSocketException(code=4403, reason=exc.detail) from exc
    if isinstance(exc, UnauthorizedError):
        raise WebSocketException(code=4401, reason=exc.detail) from exc
    raise WebSocketException(code=1013, reason=exc.detail) from exc


def _validate_allowed_roles(papel: str, allowed_roles: tuple[Role | str, ...]) -> None:
    if not allowed_roles:
        return
    allowed_values = {r.value if isinstance(r, Role) else str(r) for r in allowed_roles}
    if papel not in allowed_values:
        raise ForbiddenError(
            f"Acesso negado: o papel '{papel}' não possui permissão para este "
            f"recurso (papéis permitidos: {sorted(allowed_values)})."
        )


def _resolve_intake_principal(raw_token: str, secret_key: str) -> BearerPrincipal:
    try:
        claims = verify_intake_token(raw_token, secret_key)
    except ValueError as exc:
        raise UnauthorizedError(
            f"Token de acolhimento inválido ou expirado: {exc}."
        ) from exc

    raw_paciente = claims.get("paciente_id")
    try:
        paciente_id = UUID(str(raw_paciente))
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError(
            f"Payload do token de acolhimento inválido para paciente "
            f"'{raw_paciente}': {exc}."
        ) from exc

    return BearerPrincipal(
        actor_id=paciente_id,
        papel=Role.PACIENTE.value,
        auth_kind="intake_hmac",
        token_id=None,
        raw_token=raw_token,
        token_type="intake_provisional",  # noqa: S106
        is_intake_restrito=not bool(claims.get("is_novo_paciente", True)),
    )


async def _resolve_jwt_principal(
    raw_token: str,
    *,
    revocation: TokenRevocationPort,
    jwt_secret: str,
    jwt_algorithm: str,
    allowed_token_types: tuple[str, ...] = ("access",),
) -> BearerPrincipal:
    user = decode_access_token(
        raw_token,
        secret_key=jwt_secret,
        algorithm=jwt_algorithm,
        allowed_types=allowed_token_types,
    )
    if await revocation.is_revogado(str(user.token_id)):
        raise TokenRevogadoError(
            f"Token de acesso '{user.token_id}' revogado. Realize novo login."
        )
    return BearerPrincipal(
        actor_id=user.usuario_id,
        papel=user.papel,
        auth_kind="jwt",
        token_id=user.token_id,
        raw_token=raw_token,
        token_type=user.token_type,
    )


async def _resolve_bearer_principal_impl(
    raw_token: str | None,
    *,
    allowed_roles: tuple[Role | str, ...],
    accept_intake: bool,
    allow_restricted_intake: bool,
    allowed_token_types: tuple[str, ...],
    revocation: TokenRevocationPort,
    secret_key: str,
    jwt_secret: str,
    jwt_algorithm: str,
) -> BearerPrincipal:
    if raw_token is None or not raw_token.strip():
        raise UnauthorizedError(
            f"Credencial de autenticação não fornecida (recebido: {raw_token!r}). "
            "Envie o token no cabeçalho Authorization: Bearer <token>."
        )

    token = raw_token.strip()
    parts = token.split(".")
    if len(parts) == 2:
        if not accept_intake:
            raise UnauthorizedError(
                f"Token fornecido em formato inválido ({len(parts)} segmentos HMAC; "
                f"accept_intake={accept_intake}, esperados 3 segmentos JWT)."
            )
        principal = _resolve_intake_principal(token, secret_key)
    elif len(parts) == 3:
        principal = await _resolve_jwt_principal(
            token,
            revocation=revocation,
            jwt_secret=jwt_secret,
            jwt_algorithm=jwt_algorithm,
            allowed_token_types=allowed_token_types,
        )
    else:
        raise UnauthorizedError(
            f"Token fornecido em formato inválido ({len(parts)} segmentos; "
            "esperados 2 segmentos HMAC ou 3 segmentos JWT)."
        )

    if (
        principal.auth_kind == "intake_hmac"
        and principal.is_intake_restrito
        and not allow_restricted_intake
    ):
        raise ForbiddenError(
            "Token de acolhimento restrito para paciente já cadastrado "
            f"(paciente_id={principal.actor_id}); realize autenticação forte "
            "via OTP, Passkey ou CADSUS antes de acessar este recurso."
        )

    _validate_allowed_roles(principal.papel, allowed_roles)
    return principal


async def resolve_bearer_principal(
    raw_token: str | None,
    *,
    allowed_roles: tuple[Role | str, ...] = (),
    accept_intake: bool = False,
    allow_restricted_intake: bool = True,
    allowed_token_types: tuple[str, ...] = ("access",),
    revocation: TokenRevocationPort,
    secret_key: str,
    jwt_secret: str,
    jwt_algorithm: str = "HS256",
    transport: Literal["http", "ws"] = "http",
) -> BearerPrincipal:
    """Resolve and validate 2-part intake HMAC or 3-part JWT Bearer tokens.

    Enforces fail-closed revocation checking, role allowlist, and HTTP/WS error mapping.
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    try:
        return await _resolve_bearer_principal_impl(
            raw_token,
            allowed_roles=allowed_roles,
            accept_intake=accept_intake,
            allow_restricted_intake=allow_restricted_intake,
            allowed_token_types=allowed_token_types,
            revocation=revocation,
            secret_key=secret_key,
            jwt_secret=jwt_secret,
            jwt_algorithm=jwt_algorithm,
        )
    except DomainError as exc:
        _raise_transport_error(exc, transport)


async def _resolve_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None,
    revocation: TokenRevocationPort | None,
    auth_settings: BearerAuthSettings | None,
    *,
    allowed_token_types: tuple[str, ...],
) -> AuthenticatedUser:
    resolved_settings = auth_settings or get_bearer_auth_settings()
    resolved_revocation = revocation or get_token_revocation()
    raw_token = credentials.credentials if credentials is not None else None
    principal = await resolve_bearer_principal(
        raw_token,
        allowed_roles=(),
        accept_intake=False,
        allowed_token_types=allowed_token_types,
        revocation=resolved_revocation,
        secret_key=resolved_settings.secret_key,
        jwt_secret=resolved_settings.jwt_secret,
        jwt_algorithm=resolved_settings.jwt_algorithm,
        transport="http",
    )
    if principal.token_id is None:
        raise UnauthorizedError(
            "Token de acesso sem identificador 'jti' válido (auth_kind="
            f"'{principal.auth_kind}')."
        )
    return AuthenticatedUser(
        usuario_id=principal.actor_id,
        papel=principal.papel,
        token_id=principal.token_id,
        raw_token=principal.raw_token,
        token_type=principal.token_type,
    )


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> AuthenticatedUser:
    """Extrai e valida token Bearer verificando revogação fail-closed (ADR-013).

    Verifica assinatura JWT e blacklist distribuída via TokenRevocationPort.
    Decisões: docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    return await _resolve_authenticated_user(
        credentials,
        revocation,
        auth_settings,
        allowed_token_types=("access",),
    )


async def get_mfa_setup_or_access_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> AuthenticatedUser:
    """Resolve JWT Bearer 'access' ou 'mfa_pending' não-revogado para setup MFA.

    Permite habilitação inicial de MFA durante primeiro acesso com mfa_pending.
    Regras: ADR-007, ADR-013, docs/explanation/domains/auth-domain.md
    """
    return await _resolve_authenticated_user(
        credentials,
        revocation,
        auth_settings,
        allowed_token_types=("access", "mfa_pending"),
    )


CurrentUserDep = Annotated[AuthenticatedUser, Security(get_current_user)]
MfaSetupOrAccessUserDep = Annotated[
    AuthenticatedUser, Security(get_mfa_setup_or_access_user)
]


def require_role(*roles: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Fabrica guard de autorização macro RBAC por papéis de usuário (ADR-013).

    Regras: docs/explanation/architecture/security-and-authorization.md
    """

    def role_checker(
        current_user: Annotated[
            AuthenticatedUser,
            Security(get_current_user, scopes=list(roles)),
        ],
    ) -> AuthenticatedUser:
        if not current_user.has_role(*roles):
            allowed_roles = ", ".join(roles)
            raise ForbiddenError(
                f"Acesso negado: o papel '{current_user.papel}' não possui "
                f"autorização para este recurso. Papéis permitidos: {allowed_roles}."
            )
        return current_user

    return role_checker


def require_permission(
    *permissions: str,
) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Fabrica guard de autorização por permissões granulares de acesso (ADR-013).

    Regras: docs/explanation/architecture/security-and-authorization.md
    """

    def permission_checker(
        current_user: Annotated[
            AuthenticatedUser,
            Security(get_current_user, scopes=list(permissions)),
        ],
    ) -> AuthenticatedUser:
        missing = [p for p in permissions if not current_user.has_permission(p)]
        if missing:
            missing_str = ", ".join(missing)
            raise ForbiddenError(
                f"Acesso negado: o papel '{current_user.papel}' não possui "
                f"as seguintes permissões necessárias: {missing_str}."
            )
        return current_user

    return permission_checker
