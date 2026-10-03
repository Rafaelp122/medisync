"""Realtime WebSockets and Valkey Pub/Sub messaging infrastructure."""

import asyncio
import contextlib
import json
import logging
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
    """Publish a JSON payload to a Valkey Pub/Sub channel.

    Returns the number of clients that received the message.
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


async def forward_pubsub_to_websocket(
    valkey: "Redis",
    channel: str,
    websocket: WebSocket,
    initial_payload: dict[str, Any] | None = None,
) -> None:
    """Bridge a Valkey Pub/Sub channel to a WebSocket connection.

    Detects client disconnect immediately and unsubscribes cleanly without leaks.
    """
    pubsub = valkey.pubsub()  # pyright: ignore[reportUnknownMemberType]
    await pubsub.subscribe(channel)  # pyright: ignore[reportUnknownMemberType]

    if initial_payload is not None:
        await websocket.send_json(initial_payload)

    async def _pubsub_listener() -> None:
        async for raw_message in pubsub.listen():  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            message = cast("dict[str, object]", raw_message)
            msg_type = message.get("type")
            if msg_type == "message":
                raw_data = message.get("data")
                if isinstance(raw_data, (bytes, bytearray)):
                    text_data = raw_data.decode("utf-8")
                else:
                    text_data = str(raw_data)
                await websocket.send_text(text_data)

    async def _client_reader() -> None:
        with contextlib.suppress(WebSocketDisconnect):
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break

    listener_task = asyncio.create_task(_pubsub_listener())
    reader_task = asyncio.create_task(_client_reader())

    try:
        _done, pending = await asyncio.wait(
            [listener_task, reader_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                await task
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)  # pyright: ignore[reportUnknownMemberType]
        with contextlib.suppress(Exception):
            await pubsub.aclose()
        logger.debug("Cleaned up Pub/Sub subscription for channel '%s'", channel)
