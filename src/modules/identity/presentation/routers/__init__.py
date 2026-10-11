"""Routers for identity and onboarding endpoints."""

from src.modules.identity.presentation.routers.onboarding_router import (
    onboarding_router,
)
from src.modules.identity.presentation.routers.pacientes_router import pacientes_router
from src.modules.identity.presentation.routers.patient_auth_router import (
    patient_auth_router,
)

__all__ = ["onboarding_router", "pacientes_router", "patient_auth_router"]
