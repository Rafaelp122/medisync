"""FastAPI WebSocket endpoint for real-time patient queue position updates."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, WebSocket
from redis.asyncio import Redis

from src.core.realtime import channel_queue_patient, forward_pubsub_to_websocket
from src.core.valkey import get_valkey_pool

queue_ws_router = APIRouter(tags=["queue-realtime"])


@queue_ws_router.websocket("/ws/queue/{atendimento_id}")
async def ws_queue_patient(
    websocket: WebSocket,
    atendimento_id: UUID,
) -> None:
    """Stream real-time position updates and call events for a waiting patient."""
    await websocket.accept()
    pool = get_valkey_pool()
    client = Redis(connection_pool=pool)
    try:
        channel = channel_queue_patient(atendimento_id)
        initial_payload = {
            "event": "CONNECTED",
            "atendimento_id": str(atendimento_id),
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
