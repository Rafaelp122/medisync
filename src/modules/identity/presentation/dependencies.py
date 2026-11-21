"""Presentation layer dependencies for identity proof-of-possession verification."""

from typing import Annotated
from uuid import UUID

from fastapi import Path, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.authz import (
    OptionalBearerAuthSettingsDep,
    OptionalTokenRevocationDep,
    Role,
    get_bearer_auth_settings,
    get_token_revocation,
    http_bearer_scheme,
    resolve_bearer_principal,
)
from src.core.errors import ForbiddenError, UnauthorizedError
from src.modules.identity.presentation.schemas import Fase2Request


async def validar_intake_fase2(
    body: Fase2Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> None:
    """Validate intake token possession during Phase 2 enrichment (RN-IDE-07).

    Accepts 2-part HMAC intake tokens or 3-part PACIENTE JWTs via header or body,
    strictly rejecting corporate bypasses such as GESTOR_UNIDADE.
    Regras: docs/explanation/domains/identity-domain.md
    """
    token: str | None = (
        credentials.credentials.strip()
        if credentials and credentials.credentials
        else None
    )
    if not token and body.token:
        token = body.token.strip()

    if not token:
        raise UnauthorizedError(
            "Token de acolhimento não fornecido "
            f"(recebido credentials={credentials is not None!r}, "
            f"body_token={body.token is not None!r}; envie no cabeçalho "
            "Authorization: Bearer <token> ou no corpo da requisição)."
        )

    resolved_settings = auth_settings or get_bearer_auth_settings()
    resolved_revocation = revocation or get_token_revocation()
    principal = await resolve_bearer_principal(
        token,
        allowed_roles=(Role.PACIENTE,),
        accept_intake=True,
        revocation=resolved_revocation,
        secret_key=resolved_settings.secret_key,
        jwt_secret=resolved_settings.jwt_secret,
        jwt_algorithm=resolved_settings.jwt_algorithm,
        transport="http",
    )
    if principal.actor_id != body.paciente_id:
        raise ForbiddenError(
            "Acesso negado: o usuário autenticado não é o paciente informado "
            f"(token não confere posse sobre '{body.paciente_id}'; "
            f"autenticado='{principal.actor_id}')."
        )


async def validar_posse_titular(
    id: Annotated[UUID, Path(description="ID do paciente titular")],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> None:
    """Validate proof-of-possession for titular dependent management (RN-IDE-07).

    Accepts provisional intake tokens (2 parts HMAC) or patient JWTs (3 parts),
    strictly forbidding administrative bypasses.
    Regras: docs/explanation/domains/identity-domain.md
    """
    raw_token = (
        credentials.credentials.strip()
        if credentials and credentials.credentials
        else None
    )
    resolved_settings = auth_settings or get_bearer_auth_settings()
    resolved_revocation = revocation or get_token_revocation()
    principal = await resolve_bearer_principal(
        raw_token,
        allowed_roles=(Role.PACIENTE,),
        accept_intake=True,
        revocation=resolved_revocation,
        secret_key=resolved_settings.secret_key,
        jwt_secret=resolved_settings.jwt_secret,
        jwt_algorithm=resolved_settings.jwt_algorithm,
        transport="http",
    )
    if principal.actor_id != id:
        raise ForbiddenError(
            "Acesso negado: o usuário autenticado não é o titular informado "
            f"(token não confere posse sobre '{id}'; "
            f"autenticado='{principal.actor_id}')."
        )


ValidarIntakeFase2Dep = Annotated[None, Security(validar_intake_fase2)]
TitularPosseDep = Annotated[None, Security(validar_posse_titular)]
