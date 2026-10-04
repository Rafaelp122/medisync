"""FastAPI router for LiveKit WebRTC SFU room token issuance."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.modules.consultation.application.ports.livekit_media_port import (
    LiveKitMediaPort,
    build_participant_identity,
    build_room_name,
)
from src.modules.consultation.composition import get_livekit_adapter
from src.modules.consultation.presentation.dependencies import AtendimentoIdPath
from src.modules.consultation.presentation.schemas import (
    LiveKitTokenRequest,
    LiveKitTokenResponse,
)

livekit_router = APIRouter(prefix="/consultations", tags=["teleconsulta-webrtc"])

LiveKitAdapterDep = Annotated[LiveKitMediaPort, Depends(get_livekit_adapter)]


@livekit_router.post(
    "/{atendimento_id}/livekit/token",
    response_model=LiveKitTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Emite token JWT assinado para sala de teleconsulta no LiveKit SFU",
)
async def generate_teleconsulta_room_token(
    atendimento_id: AtendimentoIdPath,
    request: LiveKitTokenRequest,
    livekit_adapter: LiveKitAdapterDep,
) -> LiveKitTokenResponse:
    """Gera token efêmero com Video Grants para médico ou paciente entrar na sala."""
    room_name = build_room_name(
        organizacao_id=request.organizacao_id,
        atendimento_id=atendimento_id,
    )
    participant_identity = build_participant_identity(
        role=request.role,
        participant_id=request.participant_id,
    )

    token = livekit_adapter.generate_room_token(
        room_name=room_name,
        participant_identity=participant_identity,
        is_publisher=request.is_publisher,
        participant_name=request.participant_name,
        ttl_seconds=request.ttl_seconds,
    )

    server_url = getattr(livekit_adapter, "server_url", "http://localhost:7880")

    return LiveKitTokenResponse(
        token=token,
        room_name=room_name,
        participant_identity=participant_identity,
        server_url=server_url,
        expires_in=request.ttl_seconds,
    )
