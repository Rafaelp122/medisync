"""FastAPI router for LiveKit WebRTC SFU room token issuance."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from src.core.dependencies import OptionalTenantDep
from src.core.errors import ForbiddenError, TenantInvalidoError
from src.modules.consultation.application.dtos import (
    EmitirLiveKitTokenCommand,
)
from src.modules.consultation.composition import TeleconsultaServiceDep
from src.modules.consultation.presentation.dependencies import (
    AtendimentoIdPath,
    LiveKitAccessDep,
)
from src.modules.consultation.presentation.schemas import (
    LiveKitTokenRequest,
    LiveKitTokenResponse,
)

livekit_router = APIRouter(prefix="/consultations", tags=["teleconsulta-webrtc"])


@livekit_router.post(
    "/{atendimento_id}/livekit/token",
    status_code=status.HTTP_200_OK,
    summary="Emite token JWT assinado para sala de teleconsulta no LiveKit SFU",
)
async def generate_teleconsulta_room_token(
    atendimento_id: AtendimentoIdPath,
    request: Annotated[LiveKitTokenRequest, Body()],
    service: TeleconsultaServiceDep,
    _access: LiveKitAccessDep,
    tenant_id: OptionalTenantDep,
) -> LiveKitTokenResponse:
    """Gera token efêmero com Video Grants para médico ou paciente entrar na sala."""
    if (
        request.organizacao_id is not None
        and tenant_id is not None
        and request.organizacao_id != tenant_id
    ):
        raise ForbiddenError(
            f"Organização do corpo ('{request.organizacao_id}') diverge do "
            f"tenant autenticado (esperado: '{tenant_id}')."
        )
    org_id = request.organizacao_id if request.organizacao_id is not None else tenant_id
    if org_id is None:
        raise TenantInvalidoError()
    cmd = EmitirLiveKitTokenCommand(
        organizacao_id=org_id,
        atendimento_id=atendimento_id,
        participant_id=request.participant_id,
        role=request.role,
        is_publisher=request.is_publisher,
        participant_name=request.participant_name,
        ttl_seconds=request.ttl_seconds,
    )
    result = await service.emitir_token_sala(cmd)
    return LiveKitTokenResponse.model_validate(result)
