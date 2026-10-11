"""FastAPI WebSocket endpoint for real-time patient queue position updates."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket
from redis.asyncio import Redis

from src.core.realtime import channel_queue_patient, stream_channel
from src.core.valkey import get_valkey_client
from src.modules.queue.presentation.dependencies import QueueWsAuthDep

queue_ws_router = APIRouter(tags=["queue-realtime"])

ValkeyDep = Annotated[Redis, Depends(get_valkey_client)]


@queue_ws_router.websocket("/ws/queue/{atendimento_id}")
async def ws_queue_patient(
    websocket: WebSocket,
    atendimento_id: UUID,
    valkey: ValkeyDep,
    _auth: QueueWsAuthDep,
) -> None:
    """Stream real-time position updates and call events for a waiting patient."""
    await stream_channel(
        websocket,
        valkey,
        channel_queue_patient(atendimento_id),
        "CONNECTED",
        atendimento_id=str(atendimento_id),
    )
