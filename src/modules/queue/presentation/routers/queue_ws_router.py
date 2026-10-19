"""FastAPI WebSocket endpoint for real-time patient queue position updates."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, WebSocket

from src.core.dependencies import ValkeyDep
from src.core.realtime import stream_channel
from src.modules.queue.application.realtime_channels import channel_queue_patient
from src.modules.queue.presentation.dependencies import QueueWsAuthDep

queue_ws_router = APIRouter(tags=["queue-realtime"])


@queue_ws_router.websocket("/ws/queue/{atendimento_id}")
async def ws_queue_patient(
    websocket: WebSocket,
    atendimento_id: Annotated[UUID, Path(description="ID do atendimento")],
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
