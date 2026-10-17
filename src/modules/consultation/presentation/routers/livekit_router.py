"""FastAPI router for LiveKit WebRTC SFU room token issuance."""

from typing import Annotated

from fastapi import APIRouter, Body, status

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
) -> LiveKitTokenResponse:
    """Gera token efêmero com Video Grants para médico ou paciente entrar na sala."""
    cmd = EmitirLiveKitTokenCommand(
        organizacao_id=request.organizacao_id,
        atendimento_id=atendimento_id,
        participant_id=request.participant_id,
        role=request.role,
        is_publisher=request.is_publisher,
        participant_name=request.participant_name,
        ttl_seconds=request.ttl_seconds,
    )
    result = await service.emitir_token_sala(cmd)
    return LiveKitTokenResponse.model_validate(result)
