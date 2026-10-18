"""FastAPI WebSocket endpoint for doctor incoming call modal signaling."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, WebSocket

from src.core.dependencies import ValkeyDep
from src.core.realtime import stream_channel
from src.modules.consultation.application.realtime_channels import (
    channel_doctor_calls,
)
from src.modules.consultation.presentation.dependencies import DoctorWsAuthDep

doctor_ws_router = APIRouter(tags=["doctor-realtime"])


@doctor_ws_router.websocket("/ws/doctor/{medico_id}")
async def ws_doctor_calls(
    websocket: WebSocket,
    medico_id: Annotated[UUID, Path(description="ID do médico")],
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
