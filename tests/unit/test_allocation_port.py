"""Typed allocation hides Lua int codes."""

from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo

from tests.doubles import FakeLuaValkeyClient

if TYPE_CHECKING:
    from redis.asyncio import Redis


def test_alocacao_codigo_values() -> None:
    assert AlocacaoCodigo.SUCESSO == 1
    assert AlocacaoCodigo.MEDICO_OCUPADO == 0
    assert AlocacaoCodigo.INDISPONIVEL == -1


@pytest.mark.asyncio
async def test_lua_manager_expoe_metodo_tipado(tmp_path: Path) -> None:
    from src.modules.queue.infrastructure.lua_loader import LuaScriptManager

    mgr = LuaScriptManager(scripts_dir=tmp_path)
    mgr.load_script_from_string("alocar_chamada", "return 1")
    fake_client = FakeLuaValkeyClient(evalsha_outcomes=[1])
    codigo = await mgr.alocar_chamada(
        cast("Redis", fake_client), ["k1", "k2", "k3"], ["m", "a", 45]
    )
    assert codigo == AlocacaoCodigo.SUCESSO
