from typing import Annotated

from fastapi import APIRouter, Body, Request, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials

from src.core.authz import CurrentUserDep, http_bearer_scheme
from src.core.dependencies import OptionalTenantDep
from src.core.errors import NotFoundError
from src.modules.auth.application.dtos import LoginCommand
from src.modules.auth.composition import AuthServiceDep
from src.modules.auth.presentation.helpers import resolve_login_tenant_id
from src.modules.auth.presentation.schemas import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UsuarioPerfilResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["Authentication & Sessions (OWASP)"])


@auth_router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    summary="Autenticação com Argon2id e emissão de JWT (Anti-Brute Force)",
)
async def login(
    request: Request,
    body: Annotated[LoginRequest, Body()],
    service: AuthServiceDep,
    context_tenant_id: OptionalTenantDep,
) -> TokenResponse:
    """Autentica o usuário corporativo emitindo par de tokens de acesso e atualização.

    Conforme o OWASP Authentication Cheat Sheet, as respostas de erro são
    genéricas (RFC 7807) para prevenir enumeração de contas, com proteção de
    força bruta via contadores Valkey em janela deslizante.
    """
    org_id = resolve_login_tenant_id(body.organizacao_id, context_tenant_id)

    client_ip = request.client.host if request.client else "127.0.0.1"

    command = LoginCommand(
        organizacao_id=org_id,
        identificador=body.identificador,
        senha=body.senha,
        client_ip=client_ip,
    )

    tokens = await service.autenticar(command)
    return TokenResponse.model_validate(tokens)


@auth_router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    summary="Rotação de refresh token com detecção de reuso",
)
async def refresh_token(
    body: Annotated[RefreshTokenRequest, Body()],
    service: AuthServiceDep,
) -> TokenResponse:
    """Rotaciona o refresh token: invalida o token apresentado e emite um novo par."""
    tokens = await service.rotacionar_refresh_token(body.refresh_token)
    return TokenResponse.model_validate(tokens)


@auth_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revogação de sessão e logout de usuário",
)
async def logout(
    body: Annotated[RefreshTokenRequest, Body()],
    service: AuthServiceDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> Response:
    """Revoga o refresh token fornecido (e access token opcional).

    Impede renovações e acessos subsequentes em toda a malha distribuída.
    """
    access_token = credentials.credentials if credentials else None
    await service.revogar_sessao(body.refresh_token, access_token=access_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@auth_router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Perfil do usuário autenticado a partir do Bearer JWT",
)
async def me(
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> UsuarioPerfilResponse:
    """Retorna perfil do usuário ativo a partir do principal central validado."""
    cred = await service.obter_usuario_por_id(user.usuario_id, user.organizacao_id)
    if cred is None:
        raise NotFoundError("Registro de credencial do usuário não encontrado.")

    return UsuarioPerfilResponse.model_validate(cred)
