"""Presentation layer dependencies for patient queue endpoints (Issue #42)."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, WebSocket, WebSocketException

from src.core.authz.revocation import is_token_revoked
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.security import verify_intake_token
from src.modules.queue.composition import (
    PatientQueueOwnershipChecker,
    PatientQueueOwnershipCheckerDep,
)


async def validar_ws_queue_token(
    websocket: WebSocket,
    atendimento_id: UUID,
    checker: PatientQueueOwnershipCheckerDep,
    token: str | None = Query(default=None),
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
    check_fn: PatientQueueOwnershipChecker = checker  # type: ignore[assignment]
    tem_posse = await check_fn(atendimento_id, paciente_id)
    if not tem_posse:
        raise WebSocketException(
            code=4403,
            reason="Acesso negado: o token não confere posse sobre o atendimento.",
        )


QueueWsAuthDep = Annotated[None, Depends(validar_ws_queue_token)]
