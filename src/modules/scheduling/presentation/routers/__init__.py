"""Agregação de rotas HTTP do módulo scheduling (ADR-001 §7.1)."""

from fastapi import APIRouter

from src.modules.scheduling.presentation.routers.scheduling_router import (
    scheduling_router,
)

http_router = APIRouter()
http_router.include_router(scheduling_router)

__all__ = ["http_router", "scheduling_router"]
