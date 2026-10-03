"""LiveKit WebRTC SFU Adapter implementation and fake mock for testing."""

import time
import warnings
from typing import Any, cast

import httpx
import jwt

from src.core.config import get_settings
from src.modules.consultation.application.ports.livekit_media_port import (
    LiveKitMediaPort,
)


class LiveKitAdapter:
    """Production LiveKit adapter for JWT tokens and room lifecycle."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        server_url: str,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._server_url = server_url.rstrip("/")

    @property
    def server_url(self) -> str:
        """Base URL for LiveKit SFU server."""
        return self._server_url

    def generate_room_token(
        self,
        room_name: str,
        participant_identity: str,
        is_publisher: bool = True,
        participant_name: str | None = None,
        ttl_seconds: int = 3600,
    ) -> str:
        """Generate a cryptographically signed JWT token with LiveKit Video Grants."""
        now = int(time.time())
        video_grant: dict[str, Any] = {
            "room": room_name,
            "roomJoin": True,
            "canPublish": is_publisher,
            "canSubscribe": True,
            "canPublishData": True,
        }

        payload: dict[str, Any] = {
            "iss": self._api_key,
            "sub": participant_identity,
            "nbf": now - 5,
            "exp": now + ttl_seconds,
            "video": video_grant,
        }

        if participant_name:
            payload["name"] = participant_name

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=".*HMAC key is.*below the minimum recommended length.*",
            )
            raw_token = jwt.encode(  # pyright: ignore[reportUnknownMemberType]
                payload, self._api_secret, algorithm="HS256"
            )

        return raw_token

    def _generate_admin_token(
        self,
        ttl_seconds: int = 60,
        room_name: str | None = None,
    ) -> str:
        """Generate short-lived administrative JWT for Twirp RPC management."""
        now = int(time.time())
        video_grant: dict[str, Any] = {
            "roomCreate": True,
            "roomList": True,
            "roomAdmin": True,
        }
        if room_name:
            video_grant["room"] = room_name

        payload: dict[str, Any] = {
            "iss": self._api_key,
            "sub": "admin",
            "nbf": now - 5,
            "exp": now + ttl_seconds,
            "video": video_grant,
        }

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=".*HMAC key is.*below the minimum recommended length.*",
            )
            raw_token = jwt.encode(  # pyright: ignore[reportUnknownMemberType]
                payload, self._api_secret, algorithm="HS256"
            )

        return raw_token

    async def create_room(
        self,
        room_name: str,
        empty_timeout: int = 300,
        max_participants: int = 10,
    ) -> dict[str, Any]:
        """Create room on LiveKit SFU via Twirp RPC endpoint."""
        token = self._generate_admin_token(ttl_seconds=60, room_name=room_name)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "name": room_name,
            "empty_timeout": empty_timeout,
            "max_participants": max_participants,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._server_url}/twirp/livekit.RoomService/CreateRoom",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return cast("dict[str, Any]", data)

    async def delete_room(self, room_name: str) -> bool:
        """Delete room on LiveKit SFU via Twirp RPC endpoint."""
        token = self._generate_admin_token(ttl_seconds=60, room_name=room_name)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"room": room_name}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._server_url}/twirp/livekit.RoomService/DeleteRoom",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                return True
            resp.raise_for_status()
            return False

    async def list_participants(self, room_name: str) -> list[dict[str, Any]]:
        """List active participants in a room on LiveKit SFU via Twirp RPC."""
        token = self._generate_admin_token(ttl_seconds=60, room_name=room_name)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"room": room_name}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._server_url}/twirp/livekit.RoomService/ListParticipants",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "participants" in data:
                return cast("list[dict[str, Any]]", data["participants"])
            return []


class FakeLiveKitAdapter:
    """In-memory mock of LiveKit SFU port for deterministic and isolated tests."""

    def __init__(self, server_url: str = "http://fake-livekit:7880") -> None:
        self._server_url = server_url
        self.rooms: dict[str, dict[str, Any]] = {}
        self.tokens_issued: list[dict[str, Any]] = []

    @property
    def server_url(self) -> str:
        """Base URL for LiveKit SFU server."""
        return self._server_url

    def generate_room_token(
        self,
        room_name: str,
        participant_identity: str,
        is_publisher: bool = True,
        participant_name: str | None = None,
        ttl_seconds: int = 3600,
    ) -> str:
        """Emit deterministic dummy JWT string and record issuance."""
        token = f"fake-token-{room_name}-{participant_identity}"
        self.tokens_issued.append(
            {
                "room_name": room_name,
                "participant_identity": participant_identity,
                "is_publisher": is_publisher,
                "participant_name": participant_name,
                "ttl_seconds": ttl_seconds,
            }
        )
        return token

    async def create_room(
        self,
        room_name: str,
        empty_timeout: int = 300,
        max_participants: int = 10,
    ) -> dict[str, Any]:
        """Record created room in-memory."""
        room_data: dict[str, Any] = {
            "name": room_name,
            "sid": f"RM_{room_name}",
            "empty_timeout": empty_timeout,
            "max_participants": max_participants,
            "num_participants": 0,
        }
        self.rooms[room_name] = room_data
        return room_data

    async def delete_room(self, room_name: str) -> bool:
        """Delete room from in-memory registry."""
        if room_name in self.rooms:
            del self.rooms[room_name]
            return True
        return False

    async def list_participants(self, room_name: str) -> list[dict[str, Any]]:
        """Return dummy participant list."""
        if room_name in self.rooms:
            return []
        return []


def get_livekit_adapter() -> LiveKitMediaPort:
    """Factory dependency providing the configured LiveKit adapter instance."""
    settings = get_settings()
    return LiveKitAdapter(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        server_url=settings.LIVEKIT_URL,
    )
