"""FastAPI router for user authentication and session management."""

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from src.core.database import DbSessionDep
from src.core.dependencies import OptionalTenantDep
from src.core.errors import NotFoundError, UnauthorizedError
from src.modules.auth.application.dtos import LoginCommand
from src.modules.auth.application.services.auth_service import AuthService
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
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Autenticação com Argon2id e emissão de JWT (Anti-Brute Force)",
)
async def login(
    request: Request,
    body: LoginRequest,
    session: DbSessionDep,
    context_tenant_id: OptionalTenantDep,
) -> TokenResponse:
    """Autentica o usuário corporativo emitindo par de tokens de acesso e atualização.

    Conforme o OWASP Authentication Cheat Sheet, as respostas de erro são
    genéricas (RFC 7807) para prevenir enumeração de contas, com proteção de
    força bruta via contadores Valkey em janela deslizante.
    """
    org_id = resolve_login_tenant_id(body.organizacao_id, context_tenant_id)

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
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotação de refresh token com detecção de reuso",
)
async def refresh_token(
    body: RefreshTokenRequest,
    session: DbSessionDep,
) -> TokenResponse:
    """Rotaciona o refresh token: invalida o token apresentado e emite um novo par."""
    service = AuthService(session)
    tokens = await service.rotacionar_refresh_token(body.refresh_token)
    return TokenResponse.model_validate(tokens)


@auth_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revogação de sessão e logout de usuário",
)
async def logout(
    body: RefreshTokenRequest,
    session: DbSessionDep,
) -> Response:
    """Revoga o refresh token fornecido impedindo renovações futuras."""
    service = AuthService(session)
    service.revogar_sessao(body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@auth_router.get(
    "/me",
    response_model=UsuarioPerfilResponse,
    status_code=status.HTTP_200_OK,
    summary="Perfil do usuário autenticado a partir do Bearer JWT",
)
async def me(
    session: DbSessionDep,
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
