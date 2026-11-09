"""Port for ambulatory production consolidation (ADR-012)."""

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ProducaoAmbulatorialPort(Protocol):
    """Porta de aplicação para consolidação ambulatorial BPA-I (SUS).

    Permite que a finalização da consulta solicite a consolidação de produção
    pública sem acoplamento direto aos modelos internos do módulo ambulatory.
    Regras: US-11 (Consolidação Ambulatorial SUS) e ADR-012.
    """

    async def consolidar_teleconsulta(
        self,
        *,
        organizacao_id: int,
        atendimento_id: UUID,
        profissional_id: UUID,
        paciente_id: UUID,
        cnes: str | None = None,
        codigo_sigtap: str = "03.01.01.025-0",
        carater_atendimento: str = "02",
    ) -> None:
        """Consolida atendimento finalizado para faturamento BPA-I / SISAB."""
        ...
