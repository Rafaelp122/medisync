"""Application service for teleconsultation video rooms and LiveKit token issuance."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from src.modules.consultation.application.ports.livekit_media_port import (
    LiveKitMediaPort,
    build_participant_identity,
    build_room_name,
)


@dataclass(frozen=True)
class EmitirLiveKitTokenCommand:
    """Command payload for room token generation."""

    organizacao_id: int
    atendimento_id: UUID
    participant_id: UUID
    role: Literal["medico", "paciente"]
    is_publisher: bool = True
    participant_name: str | None = None
    ttl_seconds: int = 3600


@dataclass(frozen=True)
class LiveKitTokenResult:
    """Result containing the signed LiveKit room token and metadata."""

    token: str
    room_name: str
    participant_identity: str
    server_url: str
    expires_in: int


class TeleconsultaService:
    """Application service coordinating WebRTC room tokens and session access."""

    def __init__(
        self,
        media_port: LiveKitMediaPort,
        server_url: str = "http://localhost:7880",
    ) -> None:
        self._media_port = media_port
        self._server_url = server_url

    @property
    def server_url(self) -> str:
        """Return SFU server URL."""
        return self._server_url

    def emitir_token_sala(
        self,
        command: EmitirLiveKitTokenCommand,
    ) -> LiveKitTokenResult:
        """Issue signed JWT token with video grants for doctor or patient."""
        room_name = build_room_name(
            organizacao_id=command.organizacao_id,
            atendimento_id=command.atendimento_id,
        )
        participant_identity = build_participant_identity(
            role=command.role,
            participant_id=command.participant_id,
        )
        token = self._media_port.generate_room_token(
            room_name=room_name,
            participant_identity=participant_identity,
            is_publisher=command.is_publisher,
            participant_name=command.participant_name,
            ttl_seconds=command.ttl_seconds,
        )
        return LiveKitTokenResult(
            token=token,
            room_name=room_name,
            participant_identity=participant_identity,
            server_url=self._server_url,
            expires_in=command.ttl_seconds,
        )
