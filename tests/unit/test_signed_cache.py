"""SignedCachePort contract: memory adapter with TTL."""

import asyncio
from typing import TYPE_CHECKING, cast
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

from tests.doubles import FakeValkey

if TYPE_CHECKING:
    from redis.asyncio import Redis


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
    client = FakeValkey()
    cache = ValkeySignedCache(valkey=cast("Redis", client))
    doc_id = uuid4()
    assert isinstance(cache, SignedCachePort)
    assert await cache.is_assinado(doc_id) is False
    await cache.marcar_assinado(doc_id, ttl_segundos=60)
    assert await cache.is_assinado(doc_id) is True
    assert client.set_calls == [(f"doc:assinado:{doc_id}", "1", 60)]
    assert client.exists_calls == [
        (f"doc:assinado:{doc_id}",),
        (f"doc:assinado:{doc_id}",),
    ]
    assert await client.ttl(f"doc:assinado:{doc_id}") == 60
