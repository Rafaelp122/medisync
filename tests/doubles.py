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
