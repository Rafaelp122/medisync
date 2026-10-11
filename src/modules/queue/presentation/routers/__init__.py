"""Queue presentation routers."""

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

__all__ = [
    "admissao_router",
    "alocacao_router",
    "fila_router",
    "queue_ws_router",
]
