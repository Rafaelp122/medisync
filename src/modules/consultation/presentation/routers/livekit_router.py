"""FastAPI router for LiveKit WebRTC SFU room token issuance."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, ConfigDict, Field

from src.modules.consultation.application.ports.livekit_media_port import (
    LiveKitMediaPort,
    build_participant_identity,
    build_room_name,
)
from src.modules.consultation.infrastructure.livekit_adapter import get_livekit_adapter

livekit_router = APIRouter(tags=["teleconsulta-webrtc"])

LiveKitAdapterDep = Annotated[LiveKitMediaPort, Depends(get_livekit_adapter)]


class LiveKitTokenRequest(BaseModel):
    """Payload to request an authenticated LiveKit room access token."""

    model_config = ConfigDict(extra="forbid")

    organizacao_id: UUID = Field(
        description="Identificador único da organização de saúde"
    )
    participant_id: UUID = Field(
        description="Identificador único do usuário (médico ou paciente)"
    )
    role: Literal["medico", "paciente"] = Field(
        description="Papel clínico do participante"
    )
    participant_name: str | None = Field(
        default=None,
        description="Nome de exibição opcional para a sala WebRTC",
    )
    is_publisher: bool = Field(
        default=True,
        description="Habilita publicação de trilhas de áudio/vídeo",
    )
    ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Tempo de vida útil do token em segundos",
    )


class LiveKitTokenResponse(BaseModel):
    """Response containing signed JWT token and connection metadata."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(description="JWT assinado com Video Grants do LiveKit")
    room_name: str = Field(description="Nome canônico da sala org_{org}_atend_{atend}")
    participant_identity: str = Field(
        description="Identidade particionada (medico_{id} ou paciente_{id})"
    )
    server_url: str = Field(description="URL de conexão do servidor LiveKit SFU")
    expires_in: int = Field(description="Tempo de expiração do token em segundos")


@livekit_router.post(
    "/consultations/{atendimento_id}/livekit/token",
    response_model=LiveKitTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Emite token JWT assinado para sala de teleconsulta no LiveKit SFU",
)
async def generate_teleconsulta_room_token(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
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
