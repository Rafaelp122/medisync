"""Ambulatory presentation routers aggregation (ADR-001 §7.1)."""

from fastapi import APIRouter

from src.modules.ambulatory.presentation.routers.producao_router import (
    producao_router,
)

http_router = APIRouter()
http_router.include_router(producao_router)

__all__ = ["http_router", "producao_router"]
