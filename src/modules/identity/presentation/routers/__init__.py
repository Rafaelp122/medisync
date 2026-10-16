"""Routers for identity and onboarding endpoints."""

from fastapi import APIRouter

from src.modules.identity.presentation.routers.onboarding_router import (
    onboarding_router,
)
from src.modules.identity.presentation.routers.pacientes_router import pacientes_router

http_router = APIRouter()
http_router.include_router(onboarding_router)
http_router.include_router(pacientes_router)

__all__ = ["http_router", "onboarding_router", "pacientes_router"]
