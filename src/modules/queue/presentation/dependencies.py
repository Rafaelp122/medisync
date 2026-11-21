"""Presentation layer dependencies for patient queue endpoints (Issue #42)."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Security, WebSocket, WebSocketException
from fastapi.security import HTTPAuthorizationCredentials

from src.core.authz import (
    AuthenticatedUser,
    BearerAuthSettings,
    CurrentUserDep,
    OptionalBearerAuthSettingsDep,
    OptionalTokenRevocationDep,
    Role,
    TokenRevocationPort,
    get_bearer_auth_settings,
    get_token_revocation,
    http_bearer_scheme,
    resolve_bearer_principal,
)
from src.core.errors import ForbiddenError, UnauthorizedError
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
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> None:
    """Valida o handshake WebSocket da fila via parâmetro ?token= (Issue #42, ADR-013).

    Aceita token provisório de acolhimento (HMAC-SHA256, 2 partes) ou token JWT
    de acesso (papel PACIENTE, 3 partes). Rejeita com código WS 4401 ou 4403 antes
    de invocar websocket.accept().
    """
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
        transport="ws",
    )

    check_fn: PatientQueueOwnershipChecker = checker
    tem_posse = await check_fn(atendimento_id, principal.actor_id)
    if not tem_posse:
        raise WebSocketException(
            code=4403,
            reason=(
                f"Acesso negado: token do paciente '{principal.actor_id}' não confere "
                f"posse sobre o atendimento '{atendimento_id}'."
            ),
        )


QueueWsAuthDep = Annotated[None, Depends(validar_ws_queue_token)]


async def validar_admissao_paciente(
    body: AdmissaoRequest,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> None:
    """Valida posse e autorização para admissão na fila clínica (Anti-IDOR).

    Aceita token provisório de acolhimento (HMAC-SHA256, 2 partes) ou token JWT
    de acesso (papel PACIENTE ou GESTOR_UNIDADE, 3 partes).
    """
    if not credentials or not credentials.credentials:
        raise UnauthorizedError(
            "Credencial de autenticação não fornecida para admissão do paciente "
            f"'{body.paciente_id}'. Envie o token no cabeçalho "
            "Authorization: Bearer <token>."
        )

    resolved_settings = auth_settings or get_bearer_auth_settings()
    resolved_revocation = revocation or get_token_revocation()
    principal = await resolve_bearer_principal(
        credentials.credentials,
        allowed_roles=(Role.PACIENTE, Role.GESTOR_UNIDADE),
        accept_intake=True,
        revocation=resolved_revocation,
        secret_key=resolved_settings.secret_key,
        jwt_secret=resolved_settings.jwt_secret,
        jwt_algorithm=resolved_settings.jwt_algorithm,
        transport="http",
    )
    if (
        principal.papel == Role.PACIENTE.value
        and principal.actor_id != body.paciente_id
    ):
        raise ForbiddenError(
            f"Acesso negado: o usuário autenticado '{principal.actor_id}' "
            f"não é o paciente informado '{body.paciente_id}'."
        )


AdmissaoPacienteAuthDep = Annotated[None, Security(validar_admissao_paciente)]


async def exigir_medico_plantao(
    current_user: CurrentUserDep,
) -> AuthenticatedUser:
    """Garante médico no plantão autenticado (RF-03, ADR-013)."""
    if current_user.papel != Role.MEDICO:
        raise ForbiddenError(
            f"Acesso negado: o papel '{current_user.papel}' não possui "
            "autorização para chamar pacientes da fila médica; esperado 'MEDICO'."
        )
    return current_user


MedicoPlantaoAuthDep = Annotated[AuthenticatedUser, Depends(exigir_medico_plantao)]


async def _verificar_posse_token_e_atendimento(
    credentials: HTTPAuthorizationCredentials | None,
    atendimento_id: UUID,
    checker: PatientQueueOwnershipChecker,
    revocation: TokenRevocationPort | None = None,
    auth_settings: BearerAuthSettings | None = None,
) -> None:
    """Verifica credenciais e posse sobre o atendimento (Anti-IDOR)."""
    if not credentials or not credentials.credentials:
        raise UnauthorizedError(
            "Credencial de autenticação não fornecida para atendimento "
            f"'{atendimento_id}'. Envie o token no cabeçalho "
            "Authorization: Bearer <token>."
        )

    resolved_settings = auth_settings or get_bearer_auth_settings()
    resolved_revocation = revocation or get_token_revocation()
    principal = await resolve_bearer_principal(
        credentials.credentials,
        allowed_roles=(Role.PACIENTE,),
        accept_intake=True,
        revocation=resolved_revocation,
        secret_key=resolved_settings.secret_key,
        jwt_secret=resolved_settings.jwt_secret,
        jwt_algorithm=resolved_settings.jwt_algorithm,
        transport="http",
    )

    tem_posse = await checker(atendimento_id, principal.actor_id)
    if not tem_posse:
        raise ForbiddenError(
            f"Acesso negado: o usuário autenticado '{principal.actor_id}' "
            f"não possui posse sobre o atendimento '{atendimento_id}'."
        )


async def validar_posse_atendimento_path(
    atendimento_id: UUID,
    checker: PatientQueueOwnershipCheckerDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> None:
    """Valida posse do paciente sobre o atendimento informado no path (Anti-IDOR)."""
    await _verificar_posse_token_e_atendimento(
        credentials=credentials,
        atendimento_id=atendimento_id,
        checker=checker,
        revocation=revocation,
        auth_settings=auth_settings,
    )


PosseAtendimentoPathAuthDep = Annotated[None, Depends(validar_posse_atendimento_path)]


async def validar_posse_atendimento_piora(
    body: PioraClinicaRequest,
    checker: PatientQueueOwnershipCheckerDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> None:
    """Valida posse do paciente para comunicação de piora clínica (Anti-IDOR)."""
    await _verificar_posse_token_e_atendimento(
        credentials=credentials,
        atendimento_id=body.atendimento_id,
        checker=checker,
        revocation=revocation,
        auth_settings=auth_settings,
    )


PosseAtendimentoPioraAuthDep = Annotated[None, Depends(validar_posse_atendimento_piora)]
