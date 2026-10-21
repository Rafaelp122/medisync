"""Canonical test doubles and scripted in-memory adapters for unit tests."""

import asyncio
import queue as queue_module
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import UUID

from src.core.audit import AtorPapel, AtorTipo
from src.core.uuid7 import uuid7


class FakeNoneMappings:
    """Helper mappings returning None for first()."""

    def first(self) -> None:
        return None


class FakeScalarResult:
    """Scripted scalar result supporting all(), first(), and one_or_none()."""

    def __init__(self, value: Any) -> None:
        self._value: Any = value

    def all(self) -> list[Any]:
        if isinstance(self._value, list):
            return list(cast("list[Any]", self._value))
        if self._value is None:
            return []
        return [self._value]

    def first(self) -> Any:
        if isinstance(self._value, list):
            items = cast("list[Any]", self._value)
            return items[0] if items else None
        return self._value

    def one_or_none(self) -> Any:
        if isinstance(self._value, list):
            items = cast("list[Any]", self._value)
            return items[0] if items else None
        return self._value


class FakeResult:
    """Scripted session result supporting scalar and mappings access."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar_one(self) -> Any:
        assert self._value is not None
        return self._value

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self._value)

    def mappings(self) -> FakeNoneMappings:
        return FakeNoneMappings()


class FakeAddedResult:
    """Reload-after-commit result returning the first added entity."""

    def __init__(self, added: list[Any]) -> None:
        self._added = added

    def scalar_one_or_none(self) -> Any:
        return self._added[0] if self._added else None

    def scalar_one(self) -> Any:
        assert self._added
        return self._added[0]

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self._added)


class FakeAsyncSession:
    """Scripted in-memory async session with ordered execute results."""

    def __init__(
        self,
        results: list[Any] | None = None,
        added: list[Any] | None = None,
        entities: dict[Any, Any] | None = None,
    ) -> None:
        self._results: list[Any] = list(results) if results is not None else []
        self.added: list[Any] = added if added is not None else []
        self._entities: dict[Any, Any] = dict(entities) if entities is not None else {}
        self.commits: int = 0
        self.executes: int = 0

    async def get(self, entity_cls: Any, ident: Any, *args: Any, **kwargs: Any) -> Any:
        if ident in self._entities:
            return self._entities[ident]
        if (entity_cls, ident) in self._entities:
            return self._entities[(entity_cls, ident)]
        for obj in self.added:
            if getattr(obj, "id", None) == ident:
                return obj
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.executes += 1
        if self._results:
            return self._results.pop(0)
        return FakeResult(None)

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        if hasattr(obj, "id"):
            self._entities[obj.id] = obj

    def add_all(self, objs: list[Any]) -> None:
        for obj in objs:
            self.add(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj: Any) -> None:
        return None

    @asynccontextmanager
    async def begin_nested(self) -> AsyncGenerator["FakeAsyncSession", None]:
        yield self


class FakePubSub:
    """Thread-safe in-memory Pub/Sub double for forward_pubsub_to_websocket."""

    def __init__(self, queues: dict[str, queue_module.Queue[str]]) -> None:
        self._queues = queues
        self._channel: str | None = None

    async def subscribe(self, channel: str) -> None:
        self._channel = channel
        if channel not in self._queues:
            self._queues[channel] = queue_module.Queue()

    async def listen(self) -> AsyncGenerator[dict[str, object], None]:
        assert self._channel is not None
        q = self._queues[self._channel]
        while True:
            try:
                data = q.get_nowait()
            except queue_module.Empty:
                await asyncio.sleep(0.01)
                continue
            yield {"type": "message", "data": data}

    async def unsubscribe(self, channel: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


class FakePipeline:
    """In-memory Redis pipeline double for atomic operations."""

    def __init__(self, valkey: "FakeValkey") -> None:
        self._valkey = valkey

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def delete(self, *keys: str) -> "FakePipeline":
        for k in keys:
            self._valkey.delete_key(k)
        return self

    def set(self, key: str, value: Any, *args: Any, **kwargs: Any) -> "FakePipeline":
        self._valkey.set_key(key, value)
        return self

    async def execute(self) -> list[Any]:
        return []


class FakeValkey:
    """Minimal Valkey double supporting pubsub and sorted sets for in-memory tests."""

    def __init__(self) -> None:
        self._queues: dict[str, queue_module.Queue[str]] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._kv: dict[str, Any] = {}
        self._sets: dict[str, set[str]] = {}

    def delete_key(self, key: str) -> None:
        self._kv.pop(key, None)

    def set_key(self, key: str, value: Any) -> None:
        self._kv[key] = value

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)

    async def get(self, name: str) -> Any:
        return self._kv.get(name)

    async def set(self, name: str, value: Any, *args: Any, **kwargs: Any) -> bool:
        self._kv[name] = value
        return True

    async def incr(self, name: str, amount: int = 1) -> int:
        cur = int(self._kv.get(name, 0) or 0)
        self._kv[name] = cur + amount
        return cur + amount

    async def expire(self, name: str, time: int) -> bool:
        return True

    async def sadd(self, name: str, *values: str) -> int:
        s = self._sets.setdefault(name, set())
        before = len(s)
        s.update(values)
        return len(s) - before

    async def srem(self, name: str, *values: str) -> int:
        s = self._sets.get(name)
        if s is not None:
            before = len(s)
            s.difference_update(values)
            return before - len(s)
        return 0

    async def scard(self, name: str) -> int:
        s = self._sets.get(name)
        return len(s) if s is not None else 0

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self._queues)

    async def publish(self, channel: str, message: str) -> int:
        if channel not in self._queues:
            self._queues[channel] = queue_module.Queue()
        self._queues[channel].put(message)
        return 1

    async def zadd(
        self,
        name: str,
        mapping: dict[str, float | int],
        *args: Any,
        **kwargs: Any,
    ) -> int:
        if name not in self._zsets:
            self._zsets[name] = {}
        added = 0
        for member, score in mapping.items():
            if member not in self._zsets[name]:
                added += 1
            self._zsets[name][member] = float(score)
        return added

    async def zscore(self, name: str, member: str) -> float | None:
        if name not in self._zsets:
            return None
        return self._zsets[name].get(member)

    async def zrank(self, name: str, member: str) -> int | None:
        if name not in self._zsets or member not in self._zsets[name]:
            return None
        sorted_members = sorted(
            self._zsets[name].items(), key=lambda item: (item[1], item[0])
        )
        for rank, (m, _) in enumerate(sorted_members):
            if m == member:
                return rank
        return None

    async def zcard(self, name: str) -> int:
        if name not in self._zsets:
            return 0
        return len(self._zsets[name])

    async def zrem(self, name: str, *members: str) -> int:
        if name not in self._zsets:
            return 0
        removed = 0
        for m in members:
            if m in self._zsets[name]:
                del self._zsets[name][m]
                removed += 1
        return removed


class FakePDFGenerator:
    """In-memory PDF generator double implementing PDFGeneratorPort."""

    def __init__(self, content: bytes = b"%PDF-1.4 Fake PDF Content") -> None:
        self.content = content
        self.payloads: list[Any] = []
        self.calls: int = 0

    def gerar_pdf(self, payload: Any) -> bytes:
        self.calls += 1
        self.payloads.append(payload)
        return self.content


class FakeICPBrasilSigner:
    """In-memory ICP-Brasil digital signer double implementing ICPBrasilSignerPort."""

    def __init__(self, signed_suffix: bytes = b"\n%%SIGNED_ICP_BRASIL%%") -> None:
        self.signed_suffix = signed_suffix
        self.calls: list[tuple[bytes, Any, Any]] = []

    async def assinar_pdf(
        self,
        pdf_bytes: bytes,
        credenciais: Any,
        metadata: Any = None,
    ) -> bytes:
        self.calls.append((pdf_bytes, credenciais, metadata))
        return pdf_bytes + self.signed_suffix


class FakeMemoryStorage:
    """In-memory Object Storage double implementing StoragePort."""

    def __init__(self) -> None:
        self._storage: dict[str, bytes] = {}

    async def salvar_documento(
        self,
        chave: str,
        conteudo: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        self._storage[chave] = conteudo
        return chave

    async def obter_documento(self, chave: str) -> bytes:
        if chave not in self._storage:
            from src.modules.consultation.domain.exceptions import (
                DocumentoNaoEncontradoNoStorageError,
            )

            raise DocumentoNaoEncontradoNoStorageError(
                f"Documento com chave '{chave}' não encontrado no storage."
            )
        return self._storage[chave]

    async def gerar_url_pre_assinada(
        self,
        chave: str,
        expiracao_segundos: int = 300,
    ) -> str:
        if chave not in self._storage:
            from src.modules.consultation.domain.exceptions import (
                DocumentoNaoEncontradoNoStorageError,
            )

            raise DocumentoNaoEncontradoNoStorageError(
                f"Documento com chave '{chave}' não encontrado no storage."
            )
        return f"https://mock-storage.local/{chave}?expires={expiracao_segundos}"

    def contains(self, chave: str) -> bool:
        return chave in self._storage

    def clear(self) -> None:
        self._storage.clear()


class FakeArqJob:
    """In-memory ARQ Job double."""

    def __init__(self, job_id: str = "test_job_123") -> None:
        self.job_id = job_id


class FakeArqPool:
    """In-memory ARQ Redis Pool double."""

    def __init__(self, default_job_id: str = "test_job_123") -> None:
        self.default_job_id = default_job_id
        self.enqueued_jobs: list[dict[str, Any]] = []

    async def enqueue_job(
        self, function_name: str, *args: Any, **kwargs: Any
    ) -> FakeArqJob:
        self.enqueued_jobs.append(
            {"function": function_name, "args": args, "kwargs": kwargs}
        )
        return FakeArqJob(job_id=self.default_job_id)


class FakeElegibilidadeNotifier:
    """In-memory double for ElegibilidadeNotifierPort."""

    def __init__(self) -> None:
        self.eventos_falha: list[Any] = []

    async def notificar_falha(self, evento: Any) -> None:
        self.eventos_falha.append(evento)


class FakeEligibilityProvider:
    """In-memory double for EligibilityProviderPort."""

    def __init__(self, resultado: Any) -> None:
        self.resultado = resultado
        self.requisicoes: list[Any] = []

    async def verificar_elegibilidade(self, requisicao: Any) -> Any:
        self.requisicoes.append(requisicao)
        return self.resultado


class FakeAuditTrail:
    """In-memory test double implementing AuditTrailPort (ADR-007)."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def record_event(
        self,
        *,
        organizacao_id: int,
        atendimento_id: UUID,
        ator_tipo: AtorTipo | str,
        ator_papel: AtorPapel | str,
        tipo_evento: str,
        ator_id: UUID | None = None,
        estado_anterior: str | None = None,
        novo_estado: str | None = None,
        tcle_hash: str | None = None,
        payload: dict[str, Any] | None = None,
        ip_origem: str | None = None,
    ) -> UUID:
        event_id = uuid7()
        raw_tipo: Any = ator_tipo
        raw_papel: Any = ator_papel
        tipo_str: str = (
            str(raw_tipo.value) if hasattr(raw_tipo, "value") else str(raw_tipo)
        )
        papel_str: str = (
            str(raw_papel.value) if hasattr(raw_papel, "value") else str(raw_papel)
        )
        self.events.append(
            {
                "id": event_id,
                "organizacao_id": organizacao_id,
                "atendimento_id": atendimento_id,
                "ator_tipo": tipo_str,
                "ator_papel": papel_str,
                "tipo_evento": tipo_evento,
                "ator_id": ator_id,
                "estado_anterior": estado_anterior,
                "novo_estado": novo_estado,
                "tcle_hash": tcle_hash,
                "payload": payload or {},
                "ip_origem": ip_origem,
            }
        )
        return event_id

    def get_events_by_type(self, tipo_evento: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["tipo_evento"] == tipo_evento]

    def clear(self) -> None:
        self.events.clear()
