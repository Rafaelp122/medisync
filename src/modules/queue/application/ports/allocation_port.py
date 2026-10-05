"""Typed allocation port hiding Valkey Lua int codes."""

from enum import IntEnum
from typing import Any, Protocol, runtime_checkable

from src.modules.queue.application.ports.lua_script_port import LuaScriptPort


class AlocacaoCodigo(IntEnum):
    """Return codes from alocar_chamada.lua as typed enum."""

    MEDICO_OCUPADO = 0
    SUCESSO = 1
    INDISPONIVEL = -1


@runtime_checkable
class AllocationPort(LuaScriptPort, Protocol):
    """Port for typed atomic allocation without exposing Lua ints."""

    async def alocar_chamada(
        self, client: Any, keys: list[str], args: list[object]
    ) -> AlocacaoCodigo:
        """Allocate doctor/patient pair atomically.

        Args:
            client: Active Valkey/Redis async client.
            keys: KEYS array (lock medico, lock atendimento, fila).
            args: ARGV array (medico_id, atendimento_id, ttl).

        Returns:
            Typed allocation code hiding raw Lua integers.
        """
        ...
