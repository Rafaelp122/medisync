"""Unit tests for realtime Pub/Sub channel naming, formatting, and forwarder."""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect
from src.core.realtime import (
    channel_doctor_calls,
    channel_queue_patient,
    forward_pubsub_to_websocket,
    publish_realtime_event,
)


def test_canonical_channel_names() -> None:
    """Validate deterministic Valkey Pub/Sub channel naming conventions."""
    uid1 = uuid4()
    uid2 = uuid4()

    assert channel_queue_patient(uid1) == f"medisync:pubsub:queue:{uid1}"
    assert channel_doctor_calls(uid2) == f"medisync:pubsub:doctor:{uid2}"
    assert channel_queue_patient(str(uid1)) == f"medisync:pubsub:queue:{uid1}"
    assert channel_doctor_calls(str(uid2)) == f"medisync:pubsub:doctor:{uid2}"


@pytest.mark.asyncio
async def test_publish_realtime_event() -> None:
    """Verify JSON serialization and publishing to Valkey channel."""
    mock_valkey = AsyncMock()
    mock_valkey.publish.return_value = 2

    channel = "medisync:pubsub:test"
    payload = {"event": "TEST", "data": 123}

    res = await publish_realtime_event(mock_valkey, channel, payload)

    assert res == 2
    mock_valkey.publish.assert_called_once()
    call_args = mock_valkey.publish.call_args[0]
    assert call_args[0] == channel
    assert '"event": "TEST"' in call_args[1]


@pytest.mark.asyncio
async def test_forward_pubsub_to_websocket_lifecycle_and_cleanup() -> None:
    """Verify message forwarding and clean unsubscription on disconnect."""

    mock_valkey = MagicMock()
    mock_pubsub = MagicMock()
    mock_valkey.pubsub.return_value = mock_pubsub

    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()

    # Generator simulating 1 pubsub message then hanging/cancelled
    async def mock_listen() -> AsyncGenerator[dict[str, str], None]:
        yield {"type": "message", "data": '{"event": "MSG1"}'}
        # Wait until cancelled
        await asyncio.sleep(10)

    mock_pubsub.listen = mock_listen

    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock()
    mock_ws.send_text = AsyncMock()

    # Simulate client disconnect on receive
    async def mock_receive() -> dict[str, str]:
        await asyncio.sleep(0.05)
        raise WebSocketDisconnect()

    mock_ws.receive = mock_receive

    channel = "medisync:pubsub:queue:123"
    initial_payload = {"event": "CONNECTED"}

    await forward_pubsub_to_websocket(
        valkey=mock_valkey,
        channel=channel,
        websocket=mock_ws,
        initial_payload=initial_payload,
    )

    # 1. Initial payload sent
    mock_ws.send_json.assert_called_once_with(initial_payload)

    # 2. Message from pubsub forwarded
    mock_ws.send_text.assert_called_once_with('{"event": "MSG1"}')

    # 3. Clean cleanup on disconnect
    mock_pubsub.unsubscribe.assert_called_once_with(channel)
    mock_pubsub.aclose.assert_called_once()
