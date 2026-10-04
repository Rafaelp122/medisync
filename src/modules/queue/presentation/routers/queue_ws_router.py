"""FastAPI WebSocket endpoint for real-time patient queue position updates."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket
from redis.asyncio import Redis

from src.core.realtime import channel_queue_patient, stream_channel
from src.core.valkey import get_valkey_client

queue_ws_router = APIRouter(tags=["queue-realtime"])

ValkeyDep = Annotated[Redis, Depends(get_valkey_client)]


@queue_ws_router.websocket("/ws/queue/{atendimento_id}")
async def ws_queue_patient(
    websocket: WebSocket,
    atendimento_id: UUID,
    valkey: ValkeyDep,
) -> None:
    """Stream real-time position updates and call events for a waiting patient."""
    # Auth WS (issue #42) entrará como dependência antes do accept().
    await stream_channel(
        websocket,
        valkey,
        channel_queue_patient(atendimento_id),
        "CONNECTED",
        atendimento_id=str(atendimento_id),
    )
