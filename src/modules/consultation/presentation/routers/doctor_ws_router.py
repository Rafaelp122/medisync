"""FastAPI WebSocket endpoint for doctor incoming call modal signaling."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, WebSocket
from redis.asyncio import Redis

from src.core.realtime import channel_doctor_calls, forward_pubsub_to_websocket
from src.core.valkey import get_valkey_pool

doctor_ws_router = APIRouter(tags=["doctor-realtime"])


@doctor_ws_router.websocket("/ws/doctor/{medico_id}")
async def ws_doctor_calls(
    websocket: WebSocket,
    medico_id: UUID,
) -> None:
    """Stream real-time incoming call modal triggers to connected doctor client."""
    await websocket.accept()
    pool = get_valkey_pool()
    client = Redis(connection_pool=pool)
    try:
        channel = channel_doctor_calls(medico_id)
        initial_payload = {
            "event": "READY",
            "medico_id": str(medico_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await forward_pubsub_to_websocket(
            valkey=client,
            channel=channel,
            websocket=websocket,
            initial_payload=initial_payload,
        )
    finally:
        await client.aclose()
