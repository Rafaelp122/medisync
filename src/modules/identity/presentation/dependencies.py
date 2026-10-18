"""Presentation layer dependencies for identity proof-of-possession verification."""

from typing import Annotated
from uuid import UUID

from fastapi import Path, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.authz import http_bearer_scheme
from src.core.authz.revocation import is_token_revoked
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.dependencies import TenantDep
from src.core.errors import ForbiddenError, TokenRevogadoError, UnauthorizedError
from src.core.security import verify_intake_token
from src.modules.identity.presentation.schemas import Fase2Request


def _validar_intake_token(
    token: str,
    expected_paciente_id: UUID,
    tenant_id: int,
    tipo_paciente: str = "paciente",
) -> None:
    """Validate 2-part HMAC provisional intake token claims."""
    settings = get_settings()
    try:
        claims = verify_intake_token(token, settings.SECRET_KEY)
    except ValueError as exc:
        raise UnauthorizedError(str(exc)) from exc

    token_paciente_id = str(claims.get("paciente_id", ""))
    if token_paciente_id != str(expected_paciente_id):
        raise ForbiddenError(
            f"Acesso negado: o token de acolhimento não confere posse sobre o "
            f"{tipo_paciente} informado (token pertence a '{token_paciente_id}', "
            f"esperado '{expected_paciente_id}')."
        )

    token_org_id = int(claims.get("organizacao_id", 0))
    if token_org_id != tenant_id:
        raise ForbiddenError(
            f"Acesso negado: o token pertence à organização {token_org_id}, "
            f"mas o contexto solicitado é da organização {tenant_id}."
        )


async def _validar_jwt_token(
    token: str,
    expected_paciente_id: UUID,
    tenant_id: int,
    acao_permissao: str,
    tipo_paciente: str = "paciente",
) -> None:
    """Validate 3-part corporate or patient JWT access token claims."""
    user = decode_access_token(token)

    if await is_token_revoked(user.token_id):
        raise TokenRevogadoError(
            f"Token de acesso com id '{user.token_id}' revogado. Realize novo login."
        )

    if user.papel != Role.ADMIN_GLOBAL and user.organizacao_id != tenant_id:
        raise ForbiddenError(
            f"Acesso negado: o token pertence à organização {user.organizacao_id}, "
            f"mas o contexto solicitado é da organização {tenant_id}."
        )

    if user.papel in (Role.ADMIN_GLOBAL, Role.GESTOR_UNIDADE):
        return

    if user.papel != Role.PACIENTE:
        raise ForbiddenError(
            f"Acesso negado: o papel '{user.papel}' não possui permissão "
            f"para {acao_permissao}."
        )

    if user.usuario_id != expected_paciente_id:
        raise ForbiddenError(
            f"Acesso negado: o usuário autenticado não é o {tipo_paciente} informado "
            f"(usuário '{user.usuario_id}', esperado '{expected_paciente_id}')."
        )


async def validar_intake_fase2(
    body: Fase2Request,
    tenant_id: TenantDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> None:
    """Validate intake token possession during Phase 2 regulatory enrichment.

    Accepts the token via ``Authorization: Bearer <token>`` header or via
    ``body.token`` in the JSON request payload.

    Raises:
        UnauthorizedError: If token is missing, expired, or malformed (401).
        TokenRevogadoError: If access token has been revoked (401).
        ForbiddenError: If token belongs to another patient or organization (403).
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
            "Token de acolhimento não fornecido. Envie o token no cabeçalho "
            "Authorization: Bearer <token> ou no corpo da requisição."
        )

    token_parts = token.split(".")
    if len(token_parts) == 2:
        _validar_intake_token(token, body.paciente_id, tenant_id)
        return

    if len(token_parts) == 3:
        await _validar_jwt_token(
            token, body.paciente_id, tenant_id, "onboarding de paciente"
        )
        return

    raise UnauthorizedError(
        "Token fornecido em formato inválido: esperado 2 ou 3 segmentos "
        f"separados por '.', recebido {len(token_parts)} segmento(s)."
    )


async def validar_posse_titular(
    id: Annotated[UUID, Path(description="ID do paciente titular")],
    tenant_id: TenantDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> None:
    """Validate proof-of-possession for titular dependent management endpoints.

    Accepts provisional intake tokens (2 parts HMAC) or corporate/patient
    JWTs (3 parts).

    Raises:
        UnauthorizedError: If header is missing, malformed, or token is
            invalid/expired (401).
        TokenRevogadoError: If access token has been revoked (401).
        ForbiddenError: If caller lacks possession of the titular record
            or belongs to another organization (403).
    """
    if not credentials or not credentials.credentials:
        raise UnauthorizedError(
            "Credencial de acesso não fornecida. Envie o token no cabeçalho "
            "Authorization: Bearer <token>."
        )

    raw_token = credentials.credentials.strip()
    if not raw_token:
        raise UnauthorizedError(
            "Credencial de acesso não fornecida. Envie o token no cabeçalho "
            "Authorization: Bearer <token>."
        )

    token_parts = raw_token.split(".")
    if len(token_parts) == 2:
        _validar_intake_token(raw_token, id, tenant_id, tipo_paciente="titular")
        return

    if len(token_parts) == 3:
        await _validar_jwt_token(
            raw_token, id, tenant_id, "gerenciar dependentes", tipo_paciente="titular"
        )
        return

    raise UnauthorizedError(
        "Token fornecido em formato inválido: esperado 2 ou 3 segmentos "
        f"separados por '.', recebido {len(token_parts)} segmento(s)."
    )


ValidarIntakeFase2Dep = Annotated[None, Security(validar_intake_fase2)]
TitularPosseDep = Annotated[None, Security(validar_posse_titular)]
