"""Typed allocation return codes hiding raw Valkey Lua integer codes."""

from enum import IntEnum


class AlocacaoCodigo(IntEnum):
    """Return codes from alocar_chamada.lua / alocar_proximo.lua as typed enum."""

    MEDICO_OCUPADO = 0
    SUCESSO = 1
    INDISPONIVEL = -1


__all__ = ["AlocacaoCodigo"]
