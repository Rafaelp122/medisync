"""LiveKit SFU Media Port definition and room/identity canonical helpers."""

from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID


def build_room_name(organizacao_id: UUID, atendimento_id: UUID) -> str:
    """Build the canonical LiveKit room name using UUIDv7 identifiers.

    Convention: org_{organizacao_id}_atend_{atendimento_id}
    """
    return f"org_{organizacao_id}_atend_{atendimento_id}"


def build_participant_identity(
    role: Literal["medico", "paciente"],
    participant_id: UUID,
) -> str:
    """Build the canonical participant identity partitioned by clinical role.

    Convention: medico_{uuid} or paciente_{uuid}
    """
    return f"{role}_{participant_id}"


@runtime_checkable
class LiveKitMediaPort(Protocol):
    """Port for WebRTC media server token generation and room lifecycle."""

    def generate_room_token(
        self,
        room_name: str,
        participant_identity: str,
        is_publisher: bool = True,
        participant_name: str | None = None,
        ttl_seconds: int = 3600,
    ) -> str:
        """Generate a cryptographically signed JWT access token with Video Grants."""
        ...

    async def create_room(
        self,
        room_name: str,
        empty_timeout: int = 300,
        max_participants: int = 10,
    ) -> dict[str, Any]:
        """Create or initialize an active LiveKit room via Twirp RPC."""
        ...

    async def delete_room(self, room_name: str) -> bool:
        """Delete an active room and immediately disconnect all participants."""
        ...

    async def list_participants(self, room_name: str) -> list[dict[str, Any]]:
        """Retrieve current active participants connected in the room."""
        ...
