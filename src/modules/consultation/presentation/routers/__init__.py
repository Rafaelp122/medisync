"""Consultation presentation routers."""

from src.modules.consultation.presentation.routers.consultation_router import (
    consultation_router,
)
from src.modules.consultation.presentation.routers.doctor_ws_router import (
    doctor_ws_router,
)
from src.modules.consultation.presentation.routers.livekit_router import (
    livekit_router,
)

__all__ = ["consultation_router", "doctor_ws_router", "livekit_router"]
