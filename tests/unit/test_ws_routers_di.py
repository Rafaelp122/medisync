"""Unit tests for WS routers DI with shared stream_channel helper (fake Valkey)."""

import asyncio
import json
from collections.abc import AsyncGenerator
from uuid import uuid4

from fastapi.testclient import TestClient
from src.core.realtime import channel_doctor_calls, channel_queue_patient
from src.core.valkey import get_valkey_client
from src.main import create_app

from tests.doubles import FakePubSub, FakeValkey


def test_ws_queue_patient_initial_and_forward_with_fake_valkey() -> None:
    """Verify ws_queue sends CONNECTED with atendimento_id and forwards publish."""
    fake = FakeValkey()
    assert isinstance(fake.pubsub(), FakePubSub)

    async def override_valkey() -> AsyncGenerator[FakeValkey, None]:
        yield fake

    app = create_app()
    app.dependency_overrides[get_valkey_client] = override_valkey
    try:
        atend_id = uuid4()
        channel = channel_queue_patient(atend_id)
        with (
            TestClient(app) as client,
            client.websocket_connect(f"/ws/queue/{atend_id}") as ws,
        ):
            initial = ws.receive_json()
            assert initial["event"] == "CONNECTED"
            assert initial["atendimento_id"] == str(atend_id)
            assert "timestamp" in initial

            payload = {"event": "QUEUE_POSITION_UPDATE", "posicao": 2}
            asyncio.run(fake.publish(channel, json.dumps(payload)))

            received = ws.receive_json()
            assert received["event"] == "QUEUE_POSITION_UPDATE"
            assert received["posicao"] == 2
    finally:
        app.dependency_overrides.clear()


def test_ws_doctor_calls_initial_and_forward_with_fake_valkey() -> None:
    """Verify ws_doctor sends READY with medico_id and forwards publish."""
    fake = FakeValkey()

    async def override_valkey() -> AsyncGenerator[FakeValkey, None]:
        yield fake

    app = create_app()
    app.dependency_overrides[get_valkey_client] = override_valkey
    try:
        med_id = uuid4()
        atend_id = uuid4()
        channel = channel_doctor_calls(med_id)
        with (
            TestClient(app) as client,
            client.websocket_connect(f"/ws/doctor/{med_id}") as ws,
        ):
            initial = ws.receive_json()
            assert initial["event"] == "READY"
            assert initial["medico_id"] == str(med_id)
            assert "timestamp" in initial

            payload = {
                "event": "INCOMING_CALL",
                "atendimento_id": str(atend_id),
                "medico_id": str(med_id),
            }
            asyncio.run(fake.publish(channel, json.dumps(payload)))

            received = ws.receive_json()
            assert received["event"] == "INCOMING_CALL"
            assert received["atendimento_id"] == str(atend_id)
    finally:
        app.dependency_overrides.clear()
