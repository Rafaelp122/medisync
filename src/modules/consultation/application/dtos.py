"""Data Transfer Objects for the consultation module."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class LiveKitTokenRequestDTO:
    """Request DTO to generate a LiveKit room access token."""

    atendimento_id: UUID
    organizacao_id: UUID
    participant_id: UUID
    role: Literal["medico", "paciente"]
    participant_name: str | None = None
    is_publisher: bool = True
    ttl_seconds: int = 3600


@dataclass(frozen=True)
class LiveKitTokenResponseDTO:
    """Response DTO containing LiveKit access token and connection metadata."""

    token: str
    room_name: str
    participant_identity: str
    server_url: str
    expires_in: int
