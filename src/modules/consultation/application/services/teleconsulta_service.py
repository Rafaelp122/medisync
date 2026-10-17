"""Application service for teleconsultation video rooms and LiveKit token issuance."""

from src.modules.consultation.application.dtos import (
    EmitirLiveKitTokenCommand,
    LiveKitTokenResult,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
)
from src.modules.consultation.application.ports.livekit_media_port import (
    LiveKitMediaPort,
    build_participant_identity,
    build_room_name,
)


class TeleconsultaService:
    """Application service coordinating WebRTC room tokens and session access."""

    def __init__(
        self,
        media_port: LiveKitMediaPort,
        server_url: str = "http://localhost:7880",
        atendimento_reader: AtendimentoReaderPort | None = None,
    ) -> None:
        self._media_port = media_port
        self._server_url = server_url
        self._atendimento_reader = atendimento_reader

    @property
    def server_url(self) -> str:
        """Return SFU server URL."""
        return self._server_url

    async def emitir_token_sala(
        self,
        command: EmitirLiveKitTokenCommand,
    ) -> LiveKitTokenResult:
        """Issue signed JWT token with video grants for doctor or patient."""
        if command.role == "paciente" and self._atendimento_reader is not None:
            await self._atendimento_reader.atender_chamada(command.atendimento_id)

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
