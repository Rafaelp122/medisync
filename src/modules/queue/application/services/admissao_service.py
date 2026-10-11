"""Application service coordinating clinical triage and attendance admission."""

import logging
from typing import TYPE_CHECKING

from arq.connections import ArqRedis

from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdmissaoAtendimentoResult,
)
from src.modules.queue.application.ports.triage_port import TriagePort
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.application.services.fila_service import FilaService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("medisync.queue.admissao")


class AdmissaoAtendimentoService:
    """Orchestrates intake, clinical risk assessment, and atomic persistence.

    Delegates to FilaService for unified admission and queue governance (Fase 2).
    """

    def __init__(
        self,
        session: "AsyncSession",
        fila_service: FilaService,
        triage_port: TriagePort | None = None,
        controle_admissao: ControleAdmissaoService | None = None,
        arq_pool: ArqRedis | None = None,
    ) -> None:
        self._session = session
        self._fila_service = fila_service
        self._triage_port = triage_port
        self._controle_admissao = controle_admissao or getattr(
            fila_service, "controle_admissao", None
        )
        self._arq_pool = arq_pool

    @property
    def fila_service(self) -> FilaService:
        """Provide underlying queue service."""
        return self._fila_service

    async def admitir_paciente(
        self,
        command: AdmissaoAtendimentoCommand,
        *,
        raise_on_emergency: bool = True,
    ) -> AdmissaoAtendimentoResult:
        """Executes full clinical admission workflow delegating to FilaService."""
        return await self._fila_service.admitir_paciente(
            command,
            raise_on_emergency=raise_on_emergency,
        )
