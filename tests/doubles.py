"""Canonical test doubles and scripted in-memory adapters for unit tests."""

import asyncio
import queue as queue_module
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any


class FakeNoneMappings:
    """Helper mappings returning None for first()."""

    def first(self) -> None:
        return None


class FakeResult:
    """Scripted session result supporting scalar and mappings access."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar_one(self) -> Any:
        assert self._value is not None
        return self._value

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


class FakeAsyncSession:
    """Scripted in-memory async session with ordered execute results."""

    def __init__(
        self, results: list[Any] | None = None, added: list[Any] | None = None
    ) -> None:
        self._results: list[Any] = list(results) if results is not None else []
        self.added: list[Any] = added if added is not None else []
        self.commits: int = 0
        self.executes: int = 0

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.executes += 1
        if self._results:
            return self._results.pop(0)
        return FakeResult(None)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def add_all(self, objs: list[Any]) -> None:
        self.added.extend(objs)

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


class FakeValkey:
    """Minimal Valkey double supporting publish/pubsub for in-memory tests."""

    def __init__(self) -> None:
        self._queues: dict[str, queue_module.Queue[str]] = {}

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self._queues)

    async def publish(self, channel: str, message: str) -> int:
        if channel not in self._queues:
            self._queues[channel] = queue_module.Queue()
        self._queues[channel].put(message)
        return 1


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
