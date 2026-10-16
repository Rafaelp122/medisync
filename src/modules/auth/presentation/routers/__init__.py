"""Auth presentation routers re-exports."""

from fastapi import APIRouter

from src.modules.auth.presentation.routers.auth_router import auth_router
from src.modules.auth.presentation.routers.patient_auth_router import (
    patient_auth_router,
)

http_router = APIRouter()
http_router.include_router(auth_router)
http_router.include_router(patient_auth_router)

__all__ = ["auth_router", "http_router", "patient_auth_router"]
