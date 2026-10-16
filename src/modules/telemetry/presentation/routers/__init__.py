"""Telemetry presentation routers."""

from fastapi import APIRouter

from src.modules.telemetry.presentation.routers.telemetry_router import (
    telemetry_router,
)

http_router = APIRouter()
http_router.include_router(telemetry_router)

__all__ = ["http_router", "telemetry_router"]
