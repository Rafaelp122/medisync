"""Integration tests for Valkey Lua script manager and ADR-002 allocation."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from redis.asyncio import Redis
from src.core.valkey import close_valkey_pool, get_valkey_client
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager


@pytest.fixture(autouse=True)
async def cleanup_valkey() -> AsyncGenerator[None]:
    """Ensure cleanup of test keys and pools."""
    yield
    async for client in get_valkey_client():
        # Clean up test keys
        keys = await client.keys("test_org:*")  # pyright: ignore[reportUnknownMemberType]
        keys.extend(await client.keys("lock:999:*"))  # pyright: ignore[reportUnknownMemberType]
        keys.extend(await client.keys("fila:999:*"))  # pyright: ignore[reportUnknownMemberType]
        if keys:
            await client.delete(*keys)
    await close_valkey_pool()


@pytest.mark.asyncio
async def test_lua_preload_scripts_on_live_valkey() -> None:
    """Verify preloading scripts registers SHA1 on live Valkey server."""
    manager = get_lua_script_manager()
    async for client in get_valkey_client():
        loaded = await manager.preload_scripts(client)
        assert "alocar_chamada" in loaded
        sha = loaded["alocar_chamada"]
        assert len(sha) == 40

        # Verify Valkey recognizes the script
        exists = await client.script_exists(sha)
        assert exists[0] is True


@pytest.mark.asyncio
async def test_alocar_chamada_adr002_scenarios() -> None:
    """Verify all four return states of ADR-002 alocar_chamada.lua."""
    manager = get_lua_script_manager()
    org_id = 999
    medico_id = "01924b11-1111-7000-8000-000000000001"
    atendimento_id = "01924b22-2222-7000-8000-000000000002"

    k_medico_lock = f"lock:{org_id}:medico:{medico_id}"
    k_atend_lock = f"lock:{org_id}:atendimento:{atendimento_id}"
    k_fila = f"fila:{org_id}:aptos"

    async for client in get_valkey_client():
        # Setup: clear previous state
        await client.delete(k_medico_lock, k_atend_lock, k_fila)

        # --- Scenario 1: Atendimento not in queue ---
        res1 = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila],
            args=[medico_id, atendimento_id, 45],
        )
        assert res1 == -1, "Should return -1 when patient is not in queue"

        # Populate queue
        await client.zadd(k_fila, {atendimento_id: 1000})

        # --- Scenario 2: Medico already locked (busy) ---
        await client.set(k_medico_lock, "previous-call-id", ex=45)
        res2 = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila],
            args=[medico_id, atendimento_id, 45],
        )
        assert res2 == 0, (
            "Should return 0 (HTTP 409) when doctor already has active lock"
        )
        await client.delete(k_medico_lock)

        # --- Scenario 3: Atendimento already locked by another doctor ---
        await client.set(k_atend_lock, "other-medico-id", ex=45)
        res3 = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila],
            args=[medico_id, atendimento_id, 45],
        )
        assert res3 == -1, "Should return -1 when patient was locked concurrently"
        await client.delete(k_atend_lock)

        # --- Scenario 4: Successful atomic allocation ---
        res4 = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila],
            args=[medico_id, atendimento_id, 45],
        )
        assert res4 == 1, "Should return 1 on successful allocation"

        # Verify queue was removed
        assert (
            await client.zrank(k_fila, atendimento_id)  # pyright: ignore[reportUnknownMemberType]
            is None
        )

        # Verify locks and TTLs
        medico_val = await client.get(k_medico_lock)
        atend_val = await client.get(k_atend_lock)
        assert medico_val == atendimento_id
        assert atend_val == medico_id

        ttl_med = await client.ttl(k_medico_lock)
        ttl_atend = await client.ttl(k_atend_lock)
        assert 40 <= ttl_med <= 45
        assert 40 <= ttl_atend <= 45


@pytest.mark.asyncio
async def test_alocar_chamada_race_condition_zero_overbooking() -> None:
    """Stress test: 20 doctors simultaneously calling same patient = 1 winner."""
    manager = get_lua_script_manager()
    org_id = 999
    atendimento_id = "01924b33-3333-7000-8000-000000000003"
    k_fila = f"fila:{org_id}:aptos"
    k_atend_lock = f"lock:{org_id}:atendimento:{atendimento_id}"

    async for client in get_valkey_client():
        # Setup: put single patient in queue
        await client.delete(k_fila, k_atend_lock)
        await client.zadd(k_fila, {atendimento_id: 1000})

        # Preload script
        await manager.preload_scripts(client)

        async def attempt_call(doc_idx: int, cl: Redis = client) -> int:
            doc_id = f"doc-{doc_idx}"
            k_doc = f"lock:{org_id}:medico:{doc_id}"
            await cl.delete(k_doc)
            res = await manager.execute_script(
                client=cl,
                script_name="alocar_chamada",
                keys=[k_doc, k_atend_lock, k_fila],
                args=[doc_id, atendimento_id, 45],
            )
            return int(res)

        tasks = [attempt_call(i) for i in range(20)]
        results = await asyncio.gather(*tasks)

        # Invariant verification
        winners = [r for r in results if r == 1]
        losers = [r for r in results if r == -1]

        assert len(winners) == 1, f"Expected exactly 1 winner, got {len(winners)}"
        assert len(losers) == 19, f"Expected 19 losers (-1), got {len(losers)}"

        # Queue must be empty
        assert await client.zcard(k_fila) == 0

        # Clean up
        await client.delete(k_fila, k_atend_lock)


@pytest.mark.asyncio
async def test_lua_manager_self_healing_after_script_flush() -> None:
    """Verify LuaScriptManager automatically recovers when Valkey flushes scripts."""
    manager = get_lua_script_manager()
    org_id = 999
    medico_id = "doc-heal"
    atendimento_id = "atend-heal"
    k_medico_lock = f"lock:{org_id}:medico:{medico_id}"
    k_atend_lock = f"lock:{org_id}:atendimento:{atendimento_id}"
    k_fila = f"fila:{org_id}:aptos"

    async for client in get_valkey_client():
        # Setup
        await client.delete(k_medico_lock, k_atend_lock, k_fila)
        await client.zadd(k_fila, {atendimento_id: 1000})

        # Preload script initially
        await manager.preload_scripts(client)

        # Simulate Valkey restart or SCRIPT FLUSH
        await client.script_flush()

        # Execute script: should self-heal and succeed without raising NoScriptError
        res = await manager.execute_script(
            client=client,
            script_name="alocar_chamada",
            keys=[k_medico_lock, k_atend_lock, k_fila],
            args=[medico_id, atendimento_id, 45],
        )
        assert res == 1

        # Verify execution succeeded on Valkey
        assert await client.get(k_medico_lock) == atendimento_id
        await client.delete(k_medico_lock, k_atend_lock, k_fila)
