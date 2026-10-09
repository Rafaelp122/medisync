"""Queue presentation routers."""

from src.modules.queue.presentation.routers.admissao_router import (
    admissao_router,
)
from src.modules.queue.presentation.routers.queue_ws_router import (
    queue_ws_router,
)

__all__ = ["admissao_router", "queue_ws_router"]
