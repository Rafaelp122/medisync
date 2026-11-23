"""Integration tests for Valkey Lua script manager and ADR-002 4-Keys allocation."""

import asyncio
from typing import cast

import pytest
from redis.asyncio import Redis
from src.core.uuid7 import uuid7
from src.core.valkey import get_valkey_client
from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_lua_preload_scripts_on_live_valkey() -> None:
    """Verify preloading scripts registers SHA1 on live Valkey server."""
    manager = get_lua_script_manager()
    async for client in get_valkey_client():
        loaded = await manager.preload_scripts(client)
        assert "alocar_chamada" in loaded
        assert "alocar_proximo" in loaded
        sha = loaded["alocar_chamada"]
        assert len(sha) == 40

        exists = await client.script_exists(sha)
        assert exists[0] is True


@pytest.mark.asyncio
async def test_alocar_chamada_adr002_4keys_scenarios() -> None:
    """Verify all return states of ADR-002 4-Keys alocar_chamada.lua."""
    manager = get_lua_script_manager()
    medico_id = "01924b11-1111-7000-8000-000000000001"
    atendimento_id = "01924b22-2222-7000-8000-000000000002"

    k_medico_lock = f"lock:medico:{medico_id}"
    k_atend_lock = f"lock:atendimento:{atendimento_id}"
    k_consulta_lock = f"lock:consulta_ativa:medico:{medico_id}"
    k_fila = "fila:aptos"

    async for client in get_valkey_client():
        await client.delete(k_medico_lock, k_atend_lock, k_consulta_lock, k_fila)

        # Scenario 1: Atendimento not in queue
        res1 = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila, k_consulta_lock],
            args=[medico_id, atendimento_id, 45],
        )
        assert res1 == -1, "Should return -1 when patient is not in queue"

        await client.zadd(k_fila, {atendimento_id: 1000})  # pyright: ignore[reportUnknownMemberType]

        # Scenario 2a: Medico already locked in ring
        await client.set(k_medico_lock, "previous-call-id", ex=45)
        res2 = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila, k_consulta_lock],
            args=[medico_id, atendimento_id, 45],
        )
        assert res2 == 0, "Should return 0 when doctor has active ring lock"
        await client.delete(k_medico_lock)

        # Scenario 2b: Medico already in active consultation (KEYS[4])
        await client.set(k_consulta_lock, "active-consult-id", ex=7200)
        res2b = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila, k_consulta_lock],
            args=[medico_id, atendimento_id, 45],
        )
        assert res2b == 0, "Should return 0 when doctor has active consultation lock"
        await client.delete(k_consulta_lock)

        # Scenario 3: Atendimento already locked by another doctor
        await client.set(k_atend_lock, "other-medico-id", ex=45)
        res3 = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila, k_consulta_lock],
            args=[medico_id, atendimento_id, 45],
        )
        assert res3 == -1, "Should return -1 when patient was locked concurrently"
        await client.delete(k_atend_lock)

        # Scenario 4: Successful atomic allocation
        res4 = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila, k_consulta_lock],
            args=[medico_id, atendimento_id, 45],
        )
        assert res4 == 1, "Should return 1 on successful allocation"

        assert await client.zrank(k_fila, atendimento_id) is None  # pyright: ignore[reportUnknownMemberType]
        assert await client.get(k_medico_lock) == atendimento_id
        assert await client.get(k_atend_lock) == medico_id

        ttl_med = await client.ttl(k_medico_lock)
        ttl_atend = await client.ttl(k_atend_lock)
        assert 40 <= ttl_med <= 45
        assert 40 <= ttl_atend <= 45


@pytest.mark.asyncio
async def test_alocar_proximo_lua_skips_locked_and_blocks_consulta_ativa() -> None:
    """Verify alocar_proximo.lua atomically scans ZRANGE and obeys KEYS[4]."""
    manager = get_lua_script_manager()
    med_id = str(uuid7())
    atend_locked = uuid7()
    atend_free = uuid7()

    k_med_lock = f"lock:medico:{med_id}"
    k_consulta_lock = f"lock:consulta_ativa:medico:{med_id}"
    k_fila = "fila:aptos"

    async for client in get_valkey_client():
        await client.zadd(k_fila, {str(atend_locked): 1000, str(atend_free): 2000})  # pyright: ignore[reportUnknownMemberType]
        await client.set(f"lock:atendimento:{atend_locked}", "other-doc", ex=45)

        # Doctor with active consultation gets MEDICO_OCUPADO without touching ZSET
        await client.set(k_consulta_lock, "consult-123", ex=7200)
        codigo_busy, picked_busy = await manager.alocar_proximo(
            client=client,
            keys=[k_med_lock, "lock:atendimento:", k_fila, k_consulta_lock],
            args=[med_id, 45, 50],
        )
        assert codigo_busy == AlocacaoCodigo.MEDICO_OCUPADO
        assert picked_busy is None
        await client.delete(k_consulta_lock)

        # Free doctor skips locked candidate and allocates atend_free
        codigo_ok, picked_ok = await manager.alocar_proximo(
            client=client,
            keys=[k_med_lock, "lock:atendimento:", k_fila, k_consulta_lock],
            args=[med_id, 45, 50],
        )
        assert codigo_ok == AlocacaoCodigo.SUCESSO
        assert picked_ok == atend_free
        assert await client.get(k_med_lock) == str(atend_free)
        assert await client.get(f"lock:atendimento:{atend_free}") == med_id


@pytest.mark.asyncio
async def test_alocar_chamada_race_condition_zero_overbooking() -> None:
    """Stress test: 20 doctors simultaneously calling same patient = 1 winner."""
    manager = get_lua_script_manager()
    atendimento_id = "01924b33-3333-7000-8000-000000000003"
    k_fila = "fila:aptos"
    k_atend_lock = f"lock:atendimento:{atendimento_id}"

    async for client in get_valkey_client():
        await client.delete(k_fila, k_atend_lock)
        await client.zadd(k_fila, {atendimento_id: 1000})  # pyright: ignore[reportUnknownMemberType]
        await manager.preload_scripts(client)

        async def attempt_call(doc_idx: int, cl: Redis = client) -> int:
            doc_id = f"doc-{doc_idx}"
            k_doc = f"lock:medico:{doc_id}"
            k_consulta = f"lock:consulta_ativa:medico:{doc_id}"
            await cl.delete(k_doc, k_consulta)
            res = await manager.execute_script(
                client=cl,
                script_name="alocar_chamada",
                keys=[k_doc, k_atend_lock, k_fila, k_consulta],
                args=[doc_id, atendimento_id, 45],
            )
            return int(res)

        tasks = [attempt_call(i) for i in range(20)]
        results = await asyncio.gather(*tasks)

        winners = [r for r in results if r == 1]
        losers = [r for r in results if r == -1]

        assert len(winners) == 1, f"Expected exactly 1 winner, got {len(winners)}"
        assert len(losers) == 19, f"Expected 19 losers (-1), got {len(losers)}"
        assert await client.zcard(k_fila) == 0  # pyright: ignore[reportUnknownMemberType]


@pytest.mark.asyncio
async def test_lua_manager_self_healing_after_script_flush() -> None:
    """Verify LuaScriptManager automatically recovers when Valkey flushes scripts."""
    manager = get_lua_script_manager()
    medico_id = "doc-heal"
    atendimento_id = "atend-heal"
    k_medico_lock = f"lock:medico:{medico_id}"
    k_atend_lock = f"lock:atendimento:{atendimento_id}"
    k_consulta_lock = f"lock:consulta_ativa:medico:{medico_id}"
    k_fila = "fila:aptos"

    async for client in get_valkey_client():
        await client.delete(k_medico_lock, k_atend_lock, k_consulta_lock, k_fila)
        await client.zadd(k_fila, {atendimento_id: 1000})  # pyright: ignore[reportUnknownMemberType]

        await manager.preload_scripts(client)
        await client.script_flush()

        res = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila, k_consulta_lock],
            args=[medico_id, atendimento_id, 45],
        )
        assert cast("int", res) == 1
        assert await client.get(k_medico_lock) == atendimento_id
