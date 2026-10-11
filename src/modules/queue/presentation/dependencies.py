"""Presentation layer dependencies for patient queue endpoints (Issue #42)."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Security, WebSocket, WebSocketException
from fastapi.security import HTTPAuthorizationCredentials

from src.core.authz import http_bearer_scheme
from src.core.authz.dependencies import CurrentUserDep
from src.core.authz.models import AuthenticatedUser
from src.core.authz.revocation import is_token_revoked
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.dependencies import TenantDep
from src.core.errors import ForbiddenError, UnauthorizedError
from src.core.security import verify_intake_token
from src.modules.queue.composition import (
    PatientQueueOwnershipChecker,
    PatientQueueOwnershipCheckerDep,
)
from src.modules.queue.presentation.schemas import (
    AdmissaoRequest,
    PioraClinicaRequest,
)


async def validar_ws_queue_token(
    websocket: WebSocket,
    atendimento_id: UUID,
    checker: PatientQueueOwnershipCheckerDep,
    token: Annotated[
        str | None, Query(description="Token de acesso ou acolhimento")
    ] = None,
) -> None:
    """Valida o handshake WebSocket da fila via parâmetro ?token= (Issue #42).

    Aceita:
    - Token provisório de acolhimento (HMAC-SHA256, 2 partes)
    - Token JWT de acesso (papel PACIENTE ou ADMIN_GLOBAL, 3 partes)

    Rejeita requisições não autorizadas com código WS 4401 ou 4403 antes
    de invocar websocket.accept().
    """
    if not token:
        raise WebSocketException(
            code=4401,
            reason="Credencial de autenticação não fornecida.",
        )

    token_parts = token.split(".")
    if len(token_parts) == 2:
        settings = get_settings()
        try:
            claims = verify_intake_token(token, settings.SECRET_KEY)
        except ValueError as exc:
            raise WebSocketException(
                code=4401,
                reason="Token de acolhimento inválido ou expirado.",
            ) from exc

        try:
            paciente_id = UUID(str(claims["paciente_id"]))
        except Exception as exc:
            raise WebSocketException(
                code=4401,
                reason="Payload do token de acolhimento inválido.",
            ) from exc

        is_admin = False

    elif len(token_parts) == 3:
        try:
            user = decode_access_token(token)
        except Exception as exc:
            raise WebSocketException(
                code=4401,
                reason="Token de acesso inválido ou expirado.",
            ) from exc

        if await is_token_revoked(user.token_id):
            raise WebSocketException(
                code=4401,
                reason="Token de acesso revogado.",
            )

        if user.papel not in (Role.PACIENTE, Role.ADMIN_GLOBAL):
            raise WebSocketException(
                code=4403,
                reason="Acesso negado: papel não autorizado para acompanhar fila.",
            )

        paciente_id = user.usuario_id
        is_admin = user.papel == Role.ADMIN_GLOBAL

    else:
        raise WebSocketException(
            code=4401,
            reason="Formato de credencial inválido.",
        )

    # Administradores globais podem acompanhar qualquer atendimento na fila
    if is_admin:
        return

    # Validação de posse do paciente sobre o atendimento
    check_fn: PatientQueueOwnershipChecker = checker
    tem_posse = await check_fn(atendimento_id, paciente_id)
    if not tem_posse:
        raise WebSocketException(
            code=4403,
            reason="Acesso negado: o token não confere posse sobre o atendimento.",
        )


QueueWsAuthDep = Annotated[None, Depends(validar_ws_queue_token)]


async def validar_admissao_paciente(
    body: AdmissaoRequest,
    tenant_id: TenantDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> None:
    """Valida posse e autorização para admissão na fila clínica (Anti-IDOR).

    Protege contra injeção anônima de paciente_id arbitrário.
    Aceita:
    - Token provisório de acolhimento (HMAC-SHA256, 2 partes)
    - Token JWT de acesso (papel PACIENTE, GESTOR_UNIDADE ou ADMIN_GLOBAL, 3 partes)

    Rejeita requisições não autenticadas ou com paciente divergente.
    """
    if not credentials or not credentials.credentials:
        raise UnauthorizedError(
            "Credencial de autenticação não fornecida. Envie o token no cabeçalho "
            "Authorization: Bearer <token> para admissão na fila."
        )

    token = credentials.credentials
    token_parts = token.split(".")

    if len(token_parts) == 2:
        settings = get_settings()
        try:
            claims = verify_intake_token(token, settings.SECRET_KEY)
        except ValueError as exc:
            raise UnauthorizedError(f"Token de acolhimento inválido: {exc}") from exc

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

    elif len(token_parts) == 3:
        try:
            user = decode_access_token(token)
        except Exception as exc:
            raise UnauthorizedError(f"Token de acesso inválido: {exc}") from exc

        if await is_token_revoked(user.token_id):
            raise UnauthorizedError("Token de acesso revogado.")

        if user.papel not in (Role.PACIENTE, Role.ADMIN_GLOBAL, Role.GESTOR_UNIDADE):
            raise ForbiddenError(
                f"Acesso negado: papel '{user.papel}' não autorizado "
                "para admissão na fila."
            )

        if user.papel == Role.PACIENTE:
            if user.usuario_id != body.paciente_id:
                raise ForbiddenError(
                    "Acesso negado: o usuário autenticado não é o paciente informado."
                )
            if user.organizacao_id != tenant_id:
                raise ForbiddenError(
                    "Acesso negado: token pertence à organização "
                    f"{user.organizacao_id}, mas o contexto solicitado "
                    f"é da organização {tenant_id}."
                )
        elif user.papel != Role.ADMIN_GLOBAL and user.organizacao_id != tenant_id:
            raise ForbiddenError(
                "Acesso negado: token pertence à organização "
                f"{user.organizacao_id}, mas o contexto solicitado "
                f"é da organização {tenant_id}."
            )
    else:
        raise UnauthorizedError("Formato de credencial inválido.")


AdmissaoPacienteAuthDep = Annotated[None, Security(validar_admissao_paciente)]


async def exigir_medico_plantao(
    current_user: CurrentUserDep,
) -> AuthenticatedUser:
    """Garante médico no plantão ou administrador autenticado (RF-03)."""
    if current_user.papel not in (Role.MEDICO, Role.ADMIN_GLOBAL):
        raise ForbiddenError(
            f"Acesso negado: o papel '{current_user.papel}' não possui "
            "autorização para chamar pacientes da fila médica."
        )
    return current_user


MedicoPlantaoAuthDep = Annotated[AuthenticatedUser, Depends(exigir_medico_plantao)]


async def _verificar_posse_token_e_atendimento(
    credentials: HTTPAuthorizationCredentials | None,
    atendimento_id: UUID,
    tenant_id: int,
    checker: PatientQueueOwnershipChecker,
) -> None:
    """Verifica credenciais e posse sobre o atendimento (Anti-IDOR)."""
    if not credentials or not credentials.credentials:
        raise UnauthorizedError(
            "Credencial de autenticação não fornecida. Envie o token no cabeçalho "
            "Authorization: Bearer <token>."
        )

    token = credentials.credentials
    token_parts = token.split(".")

    if len(token_parts) == 2:
        settings = get_settings()
        try:
            claims = verify_intake_token(token, settings.SECRET_KEY)
        except ValueError as exc:
            raise UnauthorizedError(f"Token de acolhimento inválido: {exc}") from exc

        try:
            paciente_id = UUID(str(claims.get("paciente_id", "")))
        except Exception as exc:
            raise UnauthorizedError(
                "Payload do token de acolhimento inválido."
            ) from exc

        token_org_id = int(claims.get("organizacao_id", 0))
        if token_org_id != tenant_id:
            raise ForbiddenError(
                f"Acesso negado: o token pertence à organização {token_org_id}, "
                f"mas o contexto solicitado é da organização {tenant_id}."
            )

        tem_posse = await checker(atendimento_id, paciente_id)
        if not tem_posse:
            raise ForbiddenError(
                "Acesso negado: o token de acolhimento não confere posse "
                "sobre o atendimento."
            )

    elif len(token_parts) == 3:
        try:
            user = decode_access_token(token)
        except Exception as exc:
            raise UnauthorizedError(f"Token de acesso inválido: {exc}") from exc

        if await is_token_revoked(user.token_id):
            raise UnauthorizedError("Token de acesso revogado.")

        if user.papel == Role.ADMIN_GLOBAL:
            return

        if user.papel != Role.PACIENTE:
            raise ForbiddenError(
                f"Acesso negado: papel '{user.papel}' não autorizado "
                "para operações de paciente na fila."
            )

        if user.organizacao_id != tenant_id:
            raise ForbiddenError(
                f"Acesso negado: token pertence à organização {user.organizacao_id}, "
                f"mas o contexto solicitado é da organização {tenant_id}."
            )

        tem_posse = await checker(atendimento_id, user.usuario_id)
        if not tem_posse:
            raise ForbiddenError(
                "Acesso negado: o usuário autenticado não possui posse "
                "sobre o atendimento."
            )
    else:
        raise UnauthorizedError("Formato de credencial inválido.")


async def validar_posse_atendimento_path(
    atendimento_id: UUID,
    tenant_id: TenantDep,
    checker: PatientQueueOwnershipCheckerDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> None:
    """Valida posse do paciente sobre o atendimento informado no path (Anti-IDOR)."""
    await _verificar_posse_token_e_atendimento(
        credentials=credentials,
        atendimento_id=atendimento_id,
        tenant_id=tenant_id,
        checker=checker,
    )


PosseAtendimentoPathAuthDep = Annotated[None, Depends(validar_posse_atendimento_path)]


async def validar_posse_atendimento_piora(
    body: PioraClinicaRequest,
    tenant_id: TenantDep,
    checker: PatientQueueOwnershipCheckerDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> None:
    """Valida posse do paciente para comunicação de piora clínica (Anti-IDOR)."""
    await _verificar_posse_token_e_atendimento(
        credentials=credentials,
        atendimento_id=body.atendimento_id,
        tenant_id=tenant_id,
        checker=checker,
    )


PosseAtendimentoPioraAuthDep = Annotated[None, Depends(validar_posse_atendimento_piora)]
