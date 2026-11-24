"""Deep port for Valkey ZSET, Lua 4-Keys, quotas, sweeper locks, and Pub/Sub."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo


@runtime_checkable
class QueueEnginePort(Protocol):
    """Abstract infrastructure engine for queue operations in Valkey.

    Concentrates all key namespaces, atomic Lua 4-Keys allocation, daily quotas,
    sweeper lock coordination, active doctor presence, and Pub/Sub broadcasts.
    Regras: docs/explanation/concepts/inter-module-protocols.md
    """

    async def alocar_proximo(
        self,
        medico_id: UUID,
        ttl_segundos: int = 45,
        max_scan: int = 50,
    ) -> tuple[AlocacaoCodigo, UUID | None]:
        """Atomically scan eligible queue candidates and lock the first unlocked one."""
        ...

    async def alocar_atendimento(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
        ttl_segundos: int = 45,
    ) -> AlocacaoCodigo:
        """Atomically allocate a specific attendance using 4-Keys Lua validation."""
        ...

    async def promover_para_consulta(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
        ttl_segundos: int = 7200,
    ) -> None:
        """Promote doctor ring lock into active consultation lock and clear ring."""
        ...

    async def liberar_ring(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> None:
        """Release transient ring locks for doctor and attendance."""
        ...

    async def liberar_consulta(self, medico_id: UUID) -> None:
        """Release active consultation lock after attendance completion."""
        ...

    async def devolver_para_fila(
        self,
        atendimento_id: UUID,
        score: int,
        medico_id: UUID | None = None,
        *,
        nx: bool = False,
    ) -> bool:
        """Return an attendance to the eligible sorted set and clear transient locks."""
        ...

    async def inserir_ou_atualizar_fila(
        self,
        atendimento_id: UUID,
        score: int,
        *,
        nx: bool = False,
    ) -> int | None:
        """Insert or update an attendance score in the eligible sorted set."""
        ...

    async def remover_da_fila(self, atendimento_id: UUID) -> bool:
        """Remove an attendance from the eligible sorted set."""
        ...

    async def obter_posicao_e_tamanho(
        self,
        atendimento_id: UUID,
    ) -> tuple[int | None, int]:
        """Return 0-based rank (or None) and total queue cardinality in one pipeline."""
        ...

    async def obter_tamanho_fila(self) -> int:
        """Return current cardinality of the eligible sorted set."""
        ...

    async def consumir_cota_ou_bloquear(
        self,
        cota_diaria_maxima: int | None,
    ) -> tuple[bool, int]:
        """Atomically reserve one daily admission slot or revert if ceiling exceeded."""
        ...

    async def estornar_cota_diaria(self) -> None:
        """Compensate a reserved daily admission slot on persistence rollback."""
        ...

    async def registrar_medico_ativo(self, medico_id: UUID) -> None:
        """Register an active doctor in the shift presence set."""
        ...

    async def desregistrar_medico_ativo(self, medico_id: UUID) -> None:
        """Remove a doctor from the active shift presence set."""
        ...

    async def obter_medicos_ativos_count(self) -> int:
        """Return number of doctors currently registered as active in the shift."""
        ...

    async def publicar_evento_fila(
        self,
        atendimento_id: UUID,
        payload: dict[str, object],
    ) -> None:
        """Broadcast a realtime event to the patient queue WebSocket channel."""
        ...

    async def publicar_evento_medico(
        self,
        medico_id: UUID,
        payload: dict[str, object],
    ) -> None:
        """Broadcast a realtime call lifecycle event to the doctor WebSocket channel."""
        ...

    async def adquirir_lock_sweeper(self, ttl_segundos: int = 55) -> bool:
        """Acquire exclusive distributed lock for queue reconciliation sweeper."""
        ...

    async def liberar_lock_sweeper(self) -> None:
        """Release exclusive distributed lock held by queue reconciliation sweeper."""
        ...

    async def esta_bloqueado_para_reconciliacao(
        self,
        atendimento_id: UUID,
        medico_id: UUID | None,
    ) -> bool:
        """Check via pipeline whether queue/lock keys prevent sweeper reinjection."""
        ...


__all__ = ["QueueEnginePort"]
