"""Realtime WebSockets and Valkey Pub/Sub messaging infrastructure."""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from redis.asyncio import Redis

logger: logging.Logger = logging.getLogger("medisync.realtime")


def channel_queue_patient(atendimento_id: UUID | str) -> str:
    """Return canonical Valkey Pub/Sub channel for patient queue updates."""
    return f"medisync:pubsub:queue:{atendimento_id}"


def channel_doctor_calls(medico_id: UUID | str) -> str:
    """Return canonical Valkey Pub/Sub channel for doctor incoming calls."""
    return f"medisync:pubsub:doctor:{medico_id}"


async def publish_realtime_event(
    valkey: "Redis",
    channel: str,
    payload: dict[str, Any],
) -> int:
    """Dispara evento JSON em canal Valkey Pub/Sub para clientes conectados (ADR-002).

    Retorna a contagem de clientes receptores ativos no canal.
    Decisões: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
    """
    json_data = json.dumps(payload, ensure_ascii=False)
    subscribers_count: Any = await cast(
        "Awaitable[Any]",
        valkey.publish(channel, json_data),  # pyright: ignore[reportUnknownMemberType]
    )
    logger.debug(
        "Published realtime event to '%s' (%s subscribers)",
        channel,
        subscribers_count,
    )
    return int(cast("int", subscribers_count))


async def stream_channel(
    websocket: WebSocket,
    valkey: "Redis",
    channel: str,
    event: str,
    **ids: str,
) -> None:
    """Aceita WebSocket e ponteia canal Pub/Sub com payload inicial (ADR-002).

    Mantém streaming contínuo de atualizações clínicas em tempo real.
    Decisões: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
    """
    await websocket.accept()
    payload: dict[str, Any] = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        **ids,
    }
    await forward_pubsub_to_websocket(
        valkey=valkey,
        channel=channel,
        websocket=websocket,
        initial_payload=payload,
    )


def _formatar_dados_pubsub(raw_data: object) -> str:
    if isinstance(raw_data, (bytes, bytearray)):
        return raw_data.decode("utf-8")
    return str(raw_data)


async def _aguardar_desconexao_cliente(ws: WebSocket) -> None:
    while True:
        msg = await ws.receive()
        if msg.get("type") == "websocket.disconnect":
            return


async def _cancelar_tarefas_pendentes(tasks: set[asyncio.Task[Any]]) -> None:
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
            await task


async def forward_pubsub_to_websocket(
    valkey: "Redis",
    channel: str,
    websocket: WebSocket,
    initial_payload: dict[str, Any] | None = None,
) -> None:
    """Encaminha mensagens Pub/Sub para WebSocket com encerramento gracioso (ADR-002).

    Garante desinscrição e ausência de vazamento de conexões assíncronas.
    Decisões: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
    """
    pubsub = valkey.pubsub()  # pyright: ignore[reportUnknownMemberType]
    await pubsub.subscribe(channel)  # pyright: ignore[reportUnknownMemberType]

    if initial_payload is not None:
        await websocket.send_json(initial_payload)

    async def _pubsub_listener() -> None:
        async for raw_message in pubsub.listen():  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            message = cast("dict[str, object]", raw_message)
            if message.get("type") != "message":
                continue
            text_data = _formatar_dados_pubsub(message.get("data"))
            await websocket.send_text(text_data)

    async def _client_reader() -> None:
        with contextlib.suppress(WebSocketDisconnect):
            await _aguardar_desconexao_cliente(websocket)

    async def _heartbeat_worker() -> None:
        with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
            while True:
                await asyncio.sleep(25)
                await websocket.send_json({"type": "ping"})

    listener_task = asyncio.create_task(_pubsub_listener())
    reader_task = asyncio.create_task(_client_reader())
    heartbeat_task = asyncio.create_task(_heartbeat_worker())

    try:
        _done, pending = await asyncio.wait(
            [listener_task, reader_task, heartbeat_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        await _cancelar_tarefas_pendentes(pending)
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)  # pyright: ignore[reportUnknownMemberType]
        with contextlib.suppress(Exception):
            await pubsub.aclose()
        logger.debug("Cleaned up Pub/Sub subscription for channel '%s'", channel)
