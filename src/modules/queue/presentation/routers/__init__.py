"""Queue presentation routers."""

from fastapi import APIRouter

from src.modules.queue.presentation.routers.admissao_router import (
    admissao_router,
)
from src.modules.queue.presentation.routers.alocacao_router import (
    alocacao_router,
)
from src.modules.queue.presentation.routers.fila_router import (
    fila_router,
)
from src.modules.queue.presentation.routers.queue_ws_router import (
    queue_ws_router,
)

http_router = APIRouter()
http_router.include_router(admissao_router)
http_router.include_router(alocacao_router)
http_router.include_router(fila_router)

ws_router = APIRouter()
ws_router.include_router(queue_ws_router)

__all__ = [
    "admissao_router",
    "alocacao_router",
    "fila_router",
    "http_router",
    "queue_ws_router",
    "ws_router",
]
