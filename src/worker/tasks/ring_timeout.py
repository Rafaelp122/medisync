"""Deterministic 45-second ring timeout task for no-show resolution (RN02)."""

import logging
from typing import Any
from uuid import UUID

from src.core.context import tenant_context
from src.modules.queue.application.ports import (
    PacienteAusenteNotifierPort,
)
from src.modules.queue.composition import build_fila_service_for_session
from src.worker.context import get_db_session_from_ctx, get_valkey_from_ctx
from src.worker.tasks.base import monitored_task

logger = logging.getLogger("medisync.worker.ring_timeout")


@monitored_task
async def resolver_ring_timeout_task(
    ctx: dict[str, Any],
    organizacao_id: int,
    atendimento_id: str,
    medico_id: str,
    notifier: PacienteAusenteNotifierPort | None = None,
) -> dict[str, Any]:
    """Inspects attendance ring state after 45s; marks no-show if unanswered.

    Delegates resolution to FilaService to maintain single locality over
    queue state transitions, notifications, and Valkey locks.
    """
    valkey = get_valkey_from_ctx(ctx)
    atend_uuid = UUID(atendimento_id)
    med_uuid = UUID(medico_id)

    with tenant_context(organizacao_id):
        async with get_db_session_from_ctx(ctx) as session:
            fila_service = build_fila_service_for_session(
                valkey=valkey, session=session
            )
            action = await fila_service.resolver_ring_timeout(
                organizacao_id=organizacao_id,
                atendimento_id=atend_uuid,
                medico_id=med_uuid,
                notifier=notifier,
            )

            if action == "not_found":
                return {"status": "not_found", "action": "ignored"}

            return {
                "status": "resolved",
                "action": action,
                "atendimento_id": atendimento_id,
            }
