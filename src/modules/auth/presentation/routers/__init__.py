"""Auth presentation routers re-exports."""

from src.modules.auth.presentation.routers.auth_router import auth_router
from src.modules.auth.presentation.routers.patient_auth_router import (
    patient_auth_router,
)

__all__ = ["auth_router", "patient_auth_router"]
