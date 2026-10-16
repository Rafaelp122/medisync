"""Consultation presentation routers."""

from fastapi import APIRouter

from src.modules.consultation.presentation.routers.consultation_router import (
    consultation_router,
)
from src.modules.consultation.presentation.routers.doctor_ws_router import (
    doctor_ws_router,
)
from src.modules.consultation.presentation.routers.document_validation_router import (
    validation_router,
)
from src.modules.consultation.presentation.routers.livekit_router import (
    livekit_router,
)

http_router = APIRouter()
http_router.include_router(livekit_router)
http_router.include_router(consultation_router)
http_router.include_router(validation_router)

ws_router = APIRouter()
ws_router.include_router(doctor_ws_router)

__all__ = [
    "consultation_router",
    "doctor_ws_router",
    "http_router",
    "livekit_router",
    "validation_router",
    "ws_router",
]
