"""Unit tests for realtime Pub/Sub channel naming, formatting, and forwarder."""

import asyncio
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
from src.core.realtime import (
    forward_pubsub_to_websocket,
    publish_realtime_event,
)
from src.modules.consultation.application.realtime_channels import (
    channel_doctor_calls,
)
from src.modules.queue.application.realtime_channels import (
    channel_queue_patient,
)

from tests.doubles import FakeValkey, FakeWebSocket

if TYPE_CHECKING:
    from fastapi import WebSocket
    from redis.asyncio import Redis


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
    fake_valkey = FakeValkey()

    channel = "medisync:pubsub:test"
    payload = {"event": "TEST", "data": 123}

    res = await publish_realtime_event(cast("Redis", fake_valkey), channel, payload)

    assert res == 1
    assert len(fake_valkey.publish_calls) == 1
    published_channel, published_json = fake_valkey.publish_calls[0]
    assert published_channel == channel
    assert '"event": "TEST"' in published_json


@pytest.mark.asyncio
async def test_forward_pubsub_to_websocket_lifecycle_and_cleanup() -> None:
    """Verify message forwarding and clean unsubscription on disconnect."""
    fake_valkey = FakeValkey()
    channel = "medisync:pubsub:queue:123"
    initial_payload = {"event": "CONNECTED"}

    await fake_valkey.publish(channel, '{"event": "MSG1"}')

    fake_ws = FakeWebSocket(
        on_send_text=lambda _text: fake_ws.push_disconnect(),
    )

    await forward_pubsub_to_websocket(
        valkey=cast("Redis", fake_valkey),
        channel=channel,
        websocket=cast("WebSocket", fake_ws),
        initial_payload=initial_payload,
    )

    assert fake_ws.sent_json == [initial_payload]
    assert fake_ws.sent_text == ['{"event": "MSG1"}']
    assert fake_valkey.last_pubsub is not None
    assert channel in fake_valkey.last_pubsub.unsubscribed_channels
    assert fake_valkey.last_pubsub.closed is True


@pytest.mark.asyncio
async def test_forward_pubsub_to_websocket_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that forward_pubsub_to_websocket sends periodic heartbeat pings."""
    fake_valkey = FakeValkey()
    heartbeat_triggered = asyncio.Event()

    def _on_send_json(payload: dict[str, object]) -> None:
        if payload.get("type") == "ping":
            heartbeat_triggered.set()
            fake_ws.push_disconnect()

    fake_ws = FakeWebSocket(on_send_json=_on_send_json)

    real_sleep = asyncio.sleep

    async def fast_sleep(delay: float) -> None:
        if delay == 25:
            await real_sleep(0.01)
        else:
            await real_sleep(delay)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    await forward_pubsub_to_websocket(
        valkey=cast("Redis", fake_valkey),
        channel="medisync:pubsub:queue:test",
        websocket=cast("WebSocket", fake_ws),
    )

    assert heartbeat_triggered.is_set()


def test_core_realtime_does_not_export_channels() -> None:
    """Core realtime module must not export domain-specific channel generators."""
    import src.core.realtime as rt

    assert hasattr(rt, "channel_queue_patient") is False
    assert hasattr(rt, "channel_doctor_calls") is False
    assert hasattr(rt, "publish_realtime_event") is True
    assert hasattr(rt, "stream_channel") is True
    assert hasattr(rt, "forward_pubsub_to_websocket") is True


def test_queue_channel_patient_generation() -> None:
    """Queue module must define its canonical queue patient channel generator."""
    from src.modules.queue.application.realtime_channels import (
        channel_queue_patient,
    )

    uid = uuid4()
    assert channel_queue_patient(uid) == f"medisync:pubsub:queue:{uid}"
    assert channel_queue_patient(str(uid)) == f"medisync:pubsub:queue:{uid}"


def test_consultation_channel_doctor_calls_generation() -> None:
    """Consultation module must define its canonical doctor calls channel generator."""
    from src.modules.consultation.application.realtime_channels import (
        channel_doctor_calls,
    )

    uid = uuid4()
    assert channel_doctor_calls(uid) == f"medisync:pubsub:doctor:{uid}"
    assert channel_doctor_calls(str(uid)) == f"medisync:pubsub:doctor:{uid}"
