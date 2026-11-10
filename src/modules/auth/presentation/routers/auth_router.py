from typing import Annotated

from fastapi import APIRouter, Body, Request, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials

from src.core.authz import CurrentUserDep, http_bearer_scheme
from src.core.dependencies import OptionalTenantDep
from src.core.errors import NotFoundError, TokenInvalidoError
from src.modules.auth.application.dtos import LoginCommand
from src.modules.auth.composition import AuthServiceDep
from src.modules.auth.presentation.helpers import (
    clear_refresh_token_cookie,
    extract_refresh_token,
    resolve_login_tenant_id,
    set_refresh_token_cookie,
)
from src.modules.auth.presentation.schemas import (
    LoginRequest,
    MfaAtivarRequest,
    MfaAtivarResponse,
    MfaSetupResponse,
    MfaVerificarLoginRequest,
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
    response: Response,
    body: Annotated[LoginRequest, Body()],
    service: AuthServiceDep,
    context_tenant_id: OptionalTenantDep,
) -> TokenResponse:
    """Autentica o usuário corporativo emitindo par de tokens de acesso e atualização.

    Regras: RN-AUT-01, RN-AUT-05, RN-AUT-08, OWASP ASVS v4.0 (V3.5.2).
    Documentação: docs/explanation/domains/auth-domain.md
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
    if tokens.refresh_token:
        set_refresh_token_cookie(response, tokens.refresh_token, request=request)
    return TokenResponse.model_validate(tokens)


@auth_router.post(
    "/mfa/setup",
    status_code=status.HTTP_200_OK,
    summary="Gera chave secreta e URI para app autenticador (TOTP)",
)
async def mfa_setup(
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> MfaSetupResponse:
    """Gera o segredo Base32 e URI otpauth:// para MFA no app do usuário."""
    setup_dto = await service.gerar_mfa_secret(user.usuario_id, user.organizacao_id)
    return MfaSetupResponse.model_validate(setup_dto)


@auth_router.post(
    "/mfa/activate",
    status_code=status.HTTP_200_OK,
    summary="Valida código de 6 dígitos e ativa o segundo fator (MFA)",
)
async def mfa_activate(
    body: Annotated[MfaAtivarRequest, Body()],
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> MfaAtivarResponse:
    """Valida o primeiro código TOTP de 6 dígitos e ativa o segundo fator."""
    await service.ativar_mfa(user.usuario_id, user.organizacao_id, body.codigo)
    return MfaAtivarResponse()


@auth_router.post(
    "/mfa/verify",
    status_code=status.HTTP_200_OK,
    summary="Verificação do segundo fator (MFA) e emissão de tokens de sessão",
)
async def mfa_verify(
    request: Request,
    response: Response,
    body: Annotated[MfaVerificarLoginRequest, Body()],
    service: AuthServiceDep,
) -> TokenResponse:
    """Troca token temporário mfa_pending por tokens definitivos após validação TOTP.

    Regras: RN-AUT-04, RN-AUT-05, RN-AUT-08, OWASP ASVS v4.0 (V3.5.2).
    Documentação: docs/explanation/domains/auth-domain.md
    """
    tokens = await service.verificar_mfa_login(body.temp_token, body.codigo)
    if tokens.refresh_token:
        set_refresh_token_cookie(response, tokens.refresh_token, request=request)
    return TokenResponse.model_validate(tokens)


@auth_router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    summary="Rotação de refresh token com detecção de reuso",
)
async def refresh_token(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    body: Annotated[RefreshTokenRequest | None, Body()] = None,
) -> TokenResponse:
    """Rotaciona o refresh token: invalida o token apresentado e emite um novo par.

    Regras: RN-AUT-05, RN-AUT-08, OWASP ASVS v4.0 (V3.4.1).
    Documentação: docs/explanation/domains/auth-domain.md
    """
    token = extract_refresh_token(request, body.refresh_token if body else None)
    if not token:
        raise TokenInvalidoError(
            "Token de atualização (refresh token) não informado via cookie "
            "ou corpo da requisição."
        )
    tokens = await service.rotacionar_refresh_token(token)
    set_refresh_token_cookie(response, tokens.refresh_token, request=request)
    return TokenResponse.model_validate(tokens)


@auth_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revogação de sessão e logout de usuário",
)
async def logout(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    body: Annotated[RefreshTokenRequest | None, Body()] = None,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> Response:
    """Revoga o refresh token fornecido e expurga cookie HttpOnly síncrono.

    Regras: RN-AUT-06, OWASP ASVS v4.0 (V3.4.1).
    Documentação: docs/explanation/domains/auth-domain.md
    """
    token = extract_refresh_token(request, body.refresh_token if body else None)
    access_token = credentials.credentials if credentials else None
    if token:
        await service.revogar_sessao(token, access_token=access_token)
    clear_refresh_token_cookie(response, request=request)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


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
        raise NotFoundError(
            f"Registro de credencial do usuário '{user.usuario_id}' não encontrado."
        )

    return UsuarioPerfilResponse.model_validate(cred)
