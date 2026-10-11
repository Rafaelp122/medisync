"""Backward-compatibility re-export for patient_auth_router."""

from src.modules.auth.presentation.routers.patient_auth_router import (  # tach-ignore
    patient_auth_router,
)

__all__ = ["patient_auth_router"]
