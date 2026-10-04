"""FastAPI router for user authentication and session management."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.context import get_current_tenant_id
from src.core.database import get_db_session
from src.core.errors import NotFoundError, UnauthorizedError, ValidationError
from src.modules.auth.application.dtos import LoginCommand
from src.modules.auth.application.services.auth_service import AuthService
from src.modules.auth.presentation.schemas import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UsuarioPerfilResponse,
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]

auth_router = APIRouter(tags=["Authentication & Sessions (OWASP)"])


@auth_router.post(
    "/auth/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Autenticação com Argon2id e emissão de JWT (Anti-Brute Force)",
)
@auth_router.post(
    "/api/v1/auth/login",
    include_in_schema=False,
    response_model=TokenResponse,
)
async def login(
    request: Request,
    body: LoginRequest,
    session: SessionDep,
) -> TokenResponse:
    """Autentica o usuário corporativo emitindo par de tokens de acesso e atualização.

    Conforme o OWASP Authentication Cheat Sheet, as respostas de erro são
    genéricas (RFC 7807) para prevenir enumeração de contas, com proteção de
    força bruta via contadores Valkey em janela deslizante.
    """
    org_id = body.organizacao_id or get_current_tenant_id()
    if not org_id:
        raise ValidationError(
            "Identificador da organização (tenant) não informado "
            "(preencha no corpo ou no cabeçalho X-Tenant-ID)."
        )

    client_ip = request.client.host if request.client else "127.0.0.1"

    service = AuthService(session)
    command = LoginCommand(
        organizacao_id=org_id,
        identificador=body.identificador,
        senha=body.senha,
        client_ip=client_ip,
    )

    tokens = await service.autenticar(command)
    return TokenResponse.model_validate(tokens)


@auth_router.post(
    "/auth/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotação de refresh token com detecção de reuso",
)
@auth_router.post(
    "/api/v1/auth/refresh",
    include_in_schema=False,
    response_model=TokenResponse,
)
async def refresh_token(
    body: RefreshTokenRequest,
    session: SessionDep,
) -> TokenResponse:
    """Rotaciona o refresh token: invalida o token apresentado e emite um novo par."""
    service = AuthService(session)
    tokens = await service.rotacionar_refresh_token(body.refresh_token)
    return TokenResponse.model_validate(tokens)


@auth_router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revogação de sessão e logout de usuário",
)
@auth_router.post(
    "/api/v1/auth/logout",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    body: RefreshTokenRequest,
    session: SessionDep,
) -> Response:
    """Revoga o refresh token fornecido impedindo renovações futuras."""
    service = AuthService(session)
    service.revogar_sessao(body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@auth_router.get(
    "/auth/me",
    response_model=UsuarioPerfilResponse,
    status_code=status.HTTP_200_OK,
    summary="Perfil do usuário autenticado a partir do Bearer JWT",
)
@auth_router.get(
    "/api/v1/auth/me",
    include_in_schema=False,
    response_model=UsuarioPerfilResponse,
)
async def me(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> UsuarioPerfilResponse:
    """Valida o Bearer token JWT da requisição e retorna o perfil do usuário ativo."""
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError(
            "Cabeçalho de autorização Bearer ausente ou malformado."
        )

    token = authorization[7:].strip()
    service = AuthService(session)
    payload = service.validar_access_token(token)

    cred = await service.obter_usuario_por_id(payload.sub, payload.org_id)
    if cred is None:
        raise NotFoundError("Registro de credencial do usuário não encontrado.")

    return UsuarioPerfilResponse.model_validate(cred)
