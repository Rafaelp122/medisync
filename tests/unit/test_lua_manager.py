"""Unit tests for LuaScriptManager: loading, SHA1 caching, and resilient execution."""

import hashlib
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from redis.exceptions import NoScriptError, ResponseError
from src.modules.queue.infrastructure.lua_loader import (
    LuaScriptError,
    LuaScriptManager,
    LuaScriptNotFoundError,
    get_lua_script_manager,
)

from tests.doubles import FakeLuaValkeyClient

if TYPE_CHECKING:
    from redis.asyncio import Redis


def test_lua_manager_discovers_default_scripts() -> None:
    """Ensure LuaScriptManager discovers bundled scripts like alocar_chamada."""
    manager = LuaScriptManager()
    assert "alocar_chamada" in manager.registered_scripts
    assert "alocar_proximo" in manager.registered_scripts
    script = manager.get_script("alocar_chamada")
    assert "lock" in script
    assert "fila" in script
    assert "KEYS[4]" in script

    sha = manager.get_sha("alocar_chamada")
    assert sha is not None
    expected_sha = hashlib.sha1(script.encode("utf-8")).hexdigest()  # noqa: S324
    assert sha == expected_sha


def test_lua_manager_loads_from_custom_directory() -> None:
    """Verify loading scripts from a custom temporary directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        script_file = tmp_path / "custom_task.lua"
        script_content = "return redis.call('PING')"
        script_file.write_text(script_content, encoding="utf-8")

        manager = LuaScriptManager(scripts_dir=tmp_path)
        assert "custom_task" in manager.registered_scripts
        assert manager.get_script("custom_task") == script_content
        expected_sha = hashlib.sha1(script_content.encode("utf-8")).hexdigest()  # noqa: S324
        assert manager.get_sha("custom_task") == expected_sha


def test_lua_manager_load_string_and_missing() -> None:
    """Verify registering script from string and error handling for missing scripts."""
    manager = LuaScriptManager(scripts_dir=Path("/non-existent-dir"))
    assert manager.registered_scripts == []

    content = "return 42"
    sha = manager.load_script_from_string("answer", content)
    assert manager.get_script("answer") == content
    assert manager.get_sha("answer") == sha

    with pytest.raises(LuaScriptNotFoundError, match="not registered"):
        manager.get_script("unknown_script")

    with pytest.raises(LuaScriptNotFoundError, match="file not found"):
        manager.load_script_from_file("/invalid/path/script.lua")


def test_get_lua_script_manager_singleton() -> None:
    """Ensure get_lua_script_manager returns cached singleton."""
    m1 = get_lua_script_manager()
    m2 = get_lua_script_manager()
    assert m1 is m2


@pytest.mark.asyncio
async def test_preload_scripts() -> None:
    """Verify preload_scripts runs SCRIPT LOAD on client for registered scripts."""
    manager = LuaScriptManager(scripts_dir=Path("/non-existent-dir"))
    manager.load_script_from_string("s1", "return 1")
    manager.load_script_from_string("s2", "return 2")

    client = FakeLuaValkeyClient()
    loaded = await manager.preload_scripts(cast("Redis", client))
    assert len(loaded) == 2
    assert "s1" in loaded
    assert "s2" in loaded
    assert len(client.script_load_calls) == 2


@pytest.mark.asyncio
async def test_execute_script_success() -> None:
    """Verify execute_script runs evalsha successfully on normal path."""
    manager = LuaScriptManager(scripts_dir=Path("/non-existent-dir"))
    content = "return {KEYS[1], ARGV[1]}"
    sha = manager.load_script_from_string("test_op", content)

    client = FakeLuaValkeyClient(evalsha_outcomes=[["key1", "val1"]])

    result = await manager.execute_script(
        client=cast("Redis", client),
        script_name="test_op",
        keys=["key1"],
        args=["val1"],
    )

    assert result == ["key1", "val1"]
    assert client.evalsha_calls == [(sha, 1, ("key1", "val1"))]


@pytest.mark.asyncio
async def test_execute_script_recovers_from_noscript_error() -> None:
    """Verify execute_script catches NoScriptError, re-loads script, and retries."""
    manager = LuaScriptManager(scripts_dir=Path("/non-existent-dir"))
    content = "return 100"
    manager.load_script_from_string("self_heal", content)

    client = FakeLuaValkeyClient(
        evalsha_outcomes=[NoScriptError("NOSCRIPT No matching script."), 100],
        script_load_outcomes=["new_sha_123"],
    )

    result = await manager.execute_script(
        client=cast("Redis", client),
        script_name="self_heal",
        keys=[],
        args=[],
    )

    assert result == 100
    assert len(client.evalsha_calls) == 2
    assert client.script_load_calls == [content]
    assert manager.get_sha("self_heal") == "new_sha_123"


@pytest.mark.asyncio
async def test_execute_script_fallback_to_eval() -> None:
    """Verify fallback to eval if second evalsha also fails after reload."""
    manager = LuaScriptManager(scripts_dir=Path("/non-existent-dir"))
    content = "return 'fallback'"
    manager.load_script_from_string("fallback_test", content)

    client = FakeLuaValkeyClient(
        evalsha_outcomes=[
            NoScriptError("NOSCRIPT No matching script."),
            RuntimeError("Transient evalsha glitch"),
        ],
        script_load_outcomes=["sha_xyz"],
        eval_outcomes=["fallback"],
    )

    result = await manager.execute_script(
        client=cast("Redis", client),
        script_name="fallback_test",
        keys=["k1"],
        args=["a1"],
    )

    assert result == "fallback"
    assert client.eval_calls == [(content, 1, ("k1", "a1"))]


@pytest.mark.asyncio
async def test_execute_script_unregistered_raises_not_found() -> None:
    """Verify executing an unregistered script raises LuaScriptNotFoundError."""
    manager = LuaScriptManager(scripts_dir=Path("/non-existent-dir"))
    client = FakeLuaValkeyClient()

    with pytest.raises(LuaScriptNotFoundError, match="not registered"):
        await manager.execute_script(cast("Redis", client), "missing_script")


@pytest.mark.asyncio
async def test_execute_script_generic_response_error_wrapped() -> None:
    """Verify non-NOSCRIPT ResponseError raises LuaScriptError."""
    manager = LuaScriptManager(scripts_dir=Path("/non-existent-dir"))
    manager.load_script_from_string("syntax_err", "invalid syntax")

    client = FakeLuaValkeyClient(
        evalsha_outcomes=[ResponseError("ERR Syntax error in Lua script")]
    )

    with pytest.raises(LuaScriptError, match="Failed to execute Lua script"):
        await manager.execute_script(cast("Redis", client), "syntax_err")


@pytest.mark.asyncio
async def test_alocar_proximo_decodes_codes_and_rejects_malformed(
    tmp_path: Path,
) -> None:
    """Verify typed decoding of [code, uuid] returned by alocar_proximo.lua."""
    from src.core.uuid7 import uuid7
    from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo

    manager = LuaScriptManager(scripts_dir=tmp_path)
    manager.load_script_from_string("alocar_proximo", "return {1, ''}")
    target_id = uuid7()
    client = FakeLuaValkeyClient(
        evalsha_outcomes=[
            [1, str(target_id).encode("utf-8")],
            [0, b""],
            [-1, ""],
            "invalid-scalar",
        ]
    )
    redis_client = cast("Redis", client)

    codigo, atend_id = await manager.alocar_proximo(
        redis_client, ["k1", "k2:", "k3", "k4"], ["m1", 45, 50]
    )
    assert codigo == AlocacaoCodigo.SUCESSO
    assert atend_id == target_id

    codigo_busy, atend_busy = await manager.alocar_proximo(
        redis_client, ["k1", "k2:", "k3", "k4"], ["m1", 45, 50]
    )
    assert codigo_busy == AlocacaoCodigo.MEDICO_OCUPADO
    assert atend_busy is None

    codigo_empty, atend_empty = await manager.alocar_proximo(
        redis_client, ["k1", "k2:", "k3", "k4"], ["m1", 45, 50]
    )
    assert codigo_empty == AlocacaoCodigo.INDISPONIVEL
    assert atend_empty is None

    with pytest.raises(LuaScriptError, match="Retorno inesperado"):
        await manager.alocar_proximo(
            redis_client, ["k1", "k2:", "k3", "k4"], ["m1", 45, 50]
        )
