"""FastAPI WebSocket endpoint for doctor incoming call modal signaling."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket
from redis.asyncio import Redis

from src.core.realtime import channel_doctor_calls, stream_channel
from src.core.valkey import get_valkey_client
from src.modules.consultation.presentation.dependencies import DoctorWsAuthDep

doctor_ws_router = APIRouter(tags=["doctor-realtime"])

ValkeyDep = Annotated[Redis, Depends(get_valkey_client)]


@doctor_ws_router.websocket("/ws/doctor/{medico_id}")
async def ws_doctor_calls(
    websocket: WebSocket,
    medico_id: UUID,
    valkey: ValkeyDep,
    _auth: DoctorWsAuthDep,
) -> None:
    """Stream real-time incoming call modal triggers to connected doctor client."""
    await stream_channel(
        websocket,
        valkey,
        channel_doctor_calls(medico_id),
        "READY",
        medico_id=str(medico_id),
    )
