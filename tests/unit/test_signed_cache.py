"""SignedCachePort contract: memory adapter with TTL."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

from src.modules.consultation.application.ports.signed_cache_port import (
    SignedCachePort,
)
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)
from src.modules.consultation.infrastructure.valkey_signed_cache import (
    ValkeySignedCache,
)


async def test_memory_cache_marca_e_expira() -> None:
    cache = MemorySignedCache()
    doc_id = uuid4()
    assert await cache.is_assinado(doc_id) is False
    await cache.marcar_assinado(doc_id, ttl_segundos=1)
    assert await cache.is_assinado(doc_id) is True
    await asyncio.sleep(1.1)
    assert await cache.is_assinado(doc_id) is False


async def test_memory_cache_respeita_protocolo() -> None:
    cache = MemorySignedCache()
    assert isinstance(cache, SignedCachePort)


async def test_valkey_cache_usa_set_com_ttl_e_exists() -> None:
    client = AsyncMock()
    client.exists.return_value = 1
    cache = ValkeySignedCache(valkey=client)
    doc_id = uuid4()
    assert isinstance(cache, SignedCachePort)
    assert await cache.is_assinado(doc_id) is True
    client.exists.assert_awaited_once_with(f"doc:assinado:{doc_id}")
    await cache.marcar_assinado(doc_id, ttl_segundos=60)
    client.set.assert_awaited_once_with(f"doc:assinado:{doc_id}", "1", ex=60)
