"""Typed allocation hides Lua int codes."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo


def test_alocacao_codigo_values() -> None:
    assert AlocacaoCodigo.SUCESSO == 1
    assert AlocacaoCodigo.MEDICO_OCUPADO == 0
    assert AlocacaoCodigo.INDISPONIVEL == -1


@pytest.mark.asyncio
async def test_lua_manager_expoe_metodo_tipado(tmp_path: Path) -> None:
    from src.modules.queue.infrastructure.lua_loader import LuaScriptManager

    mgr = LuaScriptManager(scripts_dir=tmp_path)
    mgr.load_script_from_string("alocar_chamada", "return 1")
    mock_client = AsyncMock()
    mock_client.evalsha.return_value = 1
    codigo = await mgr.alocar_chamada(mock_client, ["k1", "k2", "k3"], ["m", "a", 45])
    assert codigo == AlocacaoCodigo.SUCESSO
