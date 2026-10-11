"""Unit tests for WS routers DI with auth (Issue #42)."""

import asyncio
import json
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from src.core.config import get_settings
from src.core.realtime import channel_doctor_calls, channel_queue_patient
from src.core.security import create_intake_token
from src.core.valkey import get_valkey_client
from src.main import create_app
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.queue.composition import get_patient_queue_ownership_checker
from starlette.websockets import WebSocketDisconnect

from tests.doubles import FakePubSub, FakeValkey


def _make_doctor_token(medico_id: UUID, papel: str = "MEDICO") -> str:
    service = JWTTokenService(secret_key=get_settings().JWT_SECRET_KEY)
    return service.gerar_tokens(
        usuario_id=medico_id, organizacao_id=1, papel=papel
    ).access_token


def _make_patient_token(paciente_id: UUID) -> str:
    settings = get_settings()
    return create_intake_token(paciente_id, 1, settings.SECRET_KEY)


def test_ws_queue_patient_initial_and_forward_with_fake_valkey() -> None:
    """Verify ws_queue accepts authenticated patient and forwards published events."""
    fake = FakeValkey()
    assert isinstance(fake.pubsub(), FakePubSub)

    async def override_valkey() -> AsyncGenerator[FakeValkey, None]:
        yield fake

    async def fake_posse_checker(atend_id: UUID, pac_id: UUID) -> bool:
        return True

    app = create_app()
    app.dependency_overrides[get_valkey_client] = override_valkey
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        fake_posse_checker
    )

    try:
        atend_id = uuid4()
        paciente_id = uuid4()
        token = _make_patient_token(paciente_id)
        channel = channel_queue_patient(atend_id)

        with (
            TestClient(app) as client,
            client.websocket_connect(f"/ws/queue/{atend_id}?token={token}") as ws,
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


def test_ws_queue_patient_rejected_without_token() -> None:
    """Verify ws_queue rejects unauthenticated connection with WS 4401."""
    app = create_app()
    atend_id = uuid4()

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/queue/{atend_id}"),
    ):
        pass

    assert exc_info.value.code == 4401


def test_ws_queue_patient_rejected_with_invalid_token() -> None:
    """Verify ws_queue rejects invalid token with WS 4401."""
    app = create_app()
    atend_id = uuid4()

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/queue/{atend_id}?token=invalid.token"),
    ):
        pass

    assert exc_info.value.code == 4401


def test_ws_queue_patient_rejected_with_mismatched_patient() -> None:
    """Verify ws_queue rejects patient without ownership with WS 4403."""
    fake = FakeValkey()

    async def override_valkey() -> AsyncGenerator[FakeValkey, None]:
        yield fake

    async def fake_posse_checker(atend_id: UUID, pac_id: UUID) -> bool:
        return False  # Not owner

    app = create_app()
    app.dependency_overrides[get_valkey_client] = override_valkey
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        fake_posse_checker
    )

    try:
        atend_id = uuid4()
        paciente_id = uuid4()
        token = _make_patient_token(paciente_id)

        with (
            TestClient(app) as client,
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(f"/ws/queue/{atend_id}?token={token}"),
        ):
            pass

        assert exc_info.value.code == 4403
    finally:
        app.dependency_overrides.clear()


def test_ws_doctor_calls_initial_and_forward_with_fake_valkey() -> None:
    """Verify ws_doctor accepts authenticated doctor and forwards published calls."""
    fake = FakeValkey()

    async def override_valkey() -> AsyncGenerator[FakeValkey, None]:
        yield fake

    app = create_app()
    app.dependency_overrides[get_valkey_client] = override_valkey

    try:
        med_id = uuid4()
        atend_id = uuid4()
        token = _make_doctor_token(med_id)
        channel = channel_doctor_calls(med_id)

        with (
            TestClient(app) as client,
            client.websocket_connect(f"/ws/doctor/{med_id}?token={token}") as ws,
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


def test_ws_doctor_calls_rejected_without_token() -> None:
    """Verify ws_doctor rejects unauthenticated handshake with WS 4401."""
    app = create_app()
    med_id = uuid4()

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/doctor/{med_id}"),
    ):
        pass

    assert exc_info.value.code == 4401


def test_ws_doctor_calls_rejected_with_invalid_token() -> None:
    """Verify ws_doctor rejects invalid token with WS 4401."""
    app = create_app()
    med_id = uuid4()

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/doctor/{med_id}?token=invalid.jwt.token"),
    ):
        pass

    assert exc_info.value.code == 4401


def test_ws_doctor_calls_rejected_with_mismatched_doctor_id() -> None:
    """Verify ws_doctor rejects mismatched doctor with WS 4403."""
    app = create_app()
    med_id_real = uuid4()
    med_id_outro = uuid4()
    token = _make_doctor_token(med_id_outro)

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/doctor/{med_id_real}?token={token}"),
    ):
        pass

    assert exc_info.value.code == 4403


def test_ws_doctor_calls_rejected_with_non_doctor_role() -> None:
    """Verify ws_doctor rejects token with non-doctor role with WS 4403."""
    app = create_app()
    med_id = uuid4()
    token = _make_doctor_token(med_id, papel="PACIENTE")

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/doctor/{med_id}?token={token}"),
    ):
        pass

    assert exc_info.value.code == 4403
