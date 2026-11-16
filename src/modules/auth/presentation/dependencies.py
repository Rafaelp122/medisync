"""Presentation dependencies for patient authentication across WebAuthn routes."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Security

from src.core.authz.dependencies import (
    HTTPAuthorizationCredentials,
    http_bearer_scheme,
)
from src.core.authz.revocation import is_token_revoked
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.dependencies import TenantDep
from src.core.errors import ForbiddenError, TokenRevogadoError, UnauthorizedError
from src.core.security import verify_intake_token


def _parse_intake_patient_id(raw_token: str, tenant_id: int) -> UUID:
    settings = get_settings()
    try:
        claims = verify_intake_token(raw_token, settings.SECRET_KEY)
    except ValueError as exc:
        raise UnauthorizedError(
            f"Token de acolhimento inválido ou expirado: {exc}."
        ) from exc

    token_org_id = int(claims.get("organizacao_id", 0))
    if token_org_id != tenant_id:
        raise ForbiddenError(
            f"Acesso negado: o token de acolhimento pertence à organização "
            f"{token_org_id}, mas o contexto X-Tenant-ID é {tenant_id}."
        )
    return UUID(str(claims["paciente_id"]))


async def _parse_jwt_patient_id(raw_token: str, tenant_id: int) -> UUID:
    try:
        user = decode_access_token(raw_token)
    except Exception as exc:
        raise UnauthorizedError(
            f"Token JWT de paciente inválido ou expirado: {exc}."
        ) from exc

    if await is_token_revoked(user.token_id):
        raise TokenRevogadoError(
            f"Token de acesso '{user.token_id}' revogado. Realize novo login."
        )

    if user.papel not in (Role.PACIENTE, Role.ADMIN_GLOBAL):
        raise ForbiddenError(
            f"Acesso negado: papel '{user.papel}' sem permissão para "
            f"registrar biometria de paciente (esperado: '{Role.PACIENTE.value}')."
        )

    if user.papel != Role.ADMIN_GLOBAL and user.organizacao_id != tenant_id:
        raise ForbiddenError(
            f"Acesso negado: o JWT pertence à organização {user.organizacao_id}, "
            f"mas o contexto X-Tenant-ID é {tenant_id}."
        )
    return user.usuario_id


async def require_patient_auth(
    tenant_id: TenantDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> UUID:
    """Authenticate caller using either 2-part intake HMAC token or 3-part JWT."""
    if credentials is None:
        raise UnauthorizedError(
            f"Credencial de paciente ausente (recebido: {credentials!r}; "
            "esperado 'Authorization: Bearer <token>')."
        )

    raw_token = credentials.credentials
    parts = raw_token.split(".")
    if len(parts) == 2:
        return _parse_intake_patient_id(raw_token, tenant_id)
    if len(parts) == 3:
        return await _parse_jwt_patient_id(raw_token, tenant_id)

    raise UnauthorizedError(
        f"Token em formato inválido ({len(parts)} segmentos; "
        "esperados 2 segmentos HMAC ou 3 segmentos JWT)."
    )


PatientAuthDep = Annotated[UUID, Depends(require_patient_auth)]
