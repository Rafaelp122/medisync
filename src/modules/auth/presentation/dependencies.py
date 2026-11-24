"""Presentation dependencies for patient authentication across WebAuthn routes."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Security
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
from src.core.errors import UnauthorizedError


async def require_patient_auth(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> UUID:
    """Authenticate caller using either 2-part intake HMAC token or 3-part JWT."""
    if credentials is None:
        raise UnauthorizedError(
            f"Credencial de paciente ausente (recebido: {credentials!r}; "
            "esperado 'Authorization: Bearer <token>')."
        )

    resolved_settings = auth_settings or get_bearer_auth_settings()
    resolved_revocation = revocation or get_token_revocation()
    principal = await resolve_bearer_principal(
        credentials.credentials,
        allowed_roles=(Role.PACIENTE,),
        accept_intake=True,
        allow_restricted_intake=False,
        revocation=resolved_revocation,
        secret_key=resolved_settings.secret_key,
        jwt_secret=resolved_settings.jwt_secret,
        jwt_algorithm=resolved_settings.jwt_algorithm,
        transport="http",
    )
    return principal.actor_id


PatientAuthDep = Annotated[UUID, Depends(require_patient_auth)]
