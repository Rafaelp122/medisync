"""Presentation layer dependencies for identity proof-of-possession verification."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Path

from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.dependencies import TenantDep
from src.core.errors import ForbiddenError, UnauthorizedError
from src.core.security import verify_intake_token
from src.modules.identity.presentation.schemas import Fase2Request


async def validar_intake_fase2(
    body: Fase2Request,
    tenant_id: TenantDep,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    """Validate intake token possession during Phase 2 regulatory enrichment.

    Accepts the token via ``Authorization: Bearer <token>`` header or via
    ``body.token`` in the JSON request payload.

    Raises:
        UnauthorizedError: If token is missing, expired, or malformed (401).
        ForbiddenError: If token belongs to another patient or organization (403).
    """
    token: str | None = None
    if authorization:
        parts = authorization.strip().split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise UnauthorizedError(
                "Formato do cabeçalho Authorization inválido. "
                "Esperado 'Bearer <token>'."
            )
        token = parts[1]
    elif body.token:
        token = body.token.strip()

    if not token:
        raise UnauthorizedError(
            "Token de acolhimento não fornecido. Envie o token no cabeçalho "
            "Authorization: Bearer <token> ou no corpo da requisição."
        )

    settings = get_settings()
    try:
        claims = verify_intake_token(token, settings.SECRET_KEY)
    except ValueError as exc:
        raise UnauthorizedError(str(exc)) from exc

    token_paciente_id = str(claims.get("paciente_id", ""))
    if token_paciente_id != str(body.paciente_id):
        raise ForbiddenError(
            "Acesso negado: o token de acolhimento não confere posse "
            "sobre o paciente informado."
        )

    token_org_id = int(claims.get("organizacao_id", 0))
    if token_org_id != tenant_id:
        raise ForbiddenError(
            f"Acesso negado: o token pertence à organização {token_org_id}, "
            f"mas o contexto solicitado é da organização {tenant_id}."
        )


async def validar_posse_titular(
    id: Annotated[UUID, Path(description="ID do paciente titular")],
    tenant_id: TenantDep,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    """Validate proof-of-possession for titular dependent management endpoints.

    Accepts provisional intake tokens (2 parts HMAC) or corporate/patient
    JWTs (3 parts).

    Raises:
        UnauthorizedError: If header is missing, malformed, or token is
            invalid/expired (401).
        ForbiddenError: If caller lacks possession of the titular record
            or belongs to another organization (403).
    """
    if not authorization:
        raise UnauthorizedError(
            "Credencial de acesso não fornecida. Envie o token no cabeçalho "
            "Authorization: Bearer <token>."
        )

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedError(
            "Formato do cabeçalho Authorization inválido. Esperado 'Bearer <token>'."
        )

    raw_token = parts[1]
    token_parts = raw_token.split(".")

    if len(token_parts) == 2:
        # Provisional intake token (HMAC-SHA256)
        settings = get_settings()
        try:
            claims = verify_intake_token(raw_token, settings.SECRET_KEY)
        except ValueError as exc:
            raise UnauthorizedError(str(exc)) from exc

        token_paciente_id = str(claims.get("paciente_id", ""))
        if token_paciente_id != str(id):
            raise ForbiddenError(
                "Acesso negado: o token de acolhimento não confere posse "
                "sobre o titular informado."
            )

        token_org_id = int(claims.get("organizacao_id", 0))
        if token_org_id != tenant_id:
            raise ForbiddenError(
                f"Acesso negado: o token pertence à organização {token_org_id}, "
                f"mas o contexto solicitado é da organização {tenant_id}."
            )

    elif len(token_parts) == 3:
        # Corporate or patient JWT access token
        user = decode_access_token(raw_token)

        if user.papel != Role.ADMIN_GLOBAL and user.organizacao_id != tenant_id:
            raise ForbiddenError(
                f"Acesso negado: o token pertence à organização {user.organizacao_id}, "
                f"mas o contexto solicitado é da organização {tenant_id}."
            )

        if user.papel in (Role.ADMIN_GLOBAL, Role.GESTOR_UNIDADE):
            return

        if user.papel == Role.PACIENTE:
            if user.usuario_id != id:
                raise ForbiddenError(
                    "Acesso negado: o usuário autenticado não é o titular informado."
                )
        else:
            raise ForbiddenError(
                f"Acesso negado: o papel '{user.papel}' não possui permissão "
                "para gerenciar dependentes."
            )
    else:
        raise UnauthorizedError("Token fornecido em formato inválido.")


ValidarIntakeFase2Dep = Annotated[None, Depends(validar_intake_fase2)]
TitularPosseDep = Annotated[None, Depends(validar_posse_titular)]
