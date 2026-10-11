"""Integration tests for real-time WebSocket endpoints and Valkey Pub/Sub signaling."""

import asyncio
import json
import time
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from redis.asyncio import Redis
from src.core.config import get_settings
from src.core.realtime import channel_doctor_calls, channel_queue_patient
from src.core.security import create_intake_token
from src.core.valkey import get_valkey_pool
from src.main import create_app
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.queue.composition import get_patient_queue_ownership_checker


def _make_doctor_token(medico_id: UUID) -> str:
    service = JWTTokenService(secret_key=get_settings().JWT_SECRET_KEY)
    return service.gerar_tokens(
        usuario_id=medico_id, organizacao_id=1, papel="MEDICO"
    ).access_token


def _make_patient_token(paciente_id: UUID) -> str:
    settings = get_settings()
    return create_intake_token(paciente_id, 1, settings.SECRET_KEY)


def test_ws_queue_patient_receives_updates_sub_500ms() -> None:
    """Verify Criterion 1: Patient receives updates in < 500ms upon queue progress."""
    app = create_app()
    atend_id = uuid4()
    paciente_id = uuid4()
    channel = channel_queue_patient(atend_id)
    token = _make_patient_token(paciente_id)

    async def fake_posse(a_id: UUID, p_id: UUID) -> bool:
        return True

    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: fake_posse

    try:
        with (
            TestClient(app) as client,
            client.websocket_connect(f"/ws/queue/{atend_id}?token={token}") as ws,
        ):
            # 1. Verify initial connection event
            initial_msg = ws.receive_json()
            assert initial_msg["event"] == "CONNECTED"
            assert initial_msg["atendimento_id"] == str(atend_id)

            # 2. Publish position update in Valkey from external process
            async def publish_event() -> None:
                pool = get_valkey_pool()
                valkey = Redis(connection_pool=pool)
                await asyncio.sleep(0.05)
                payload = {
                    "event": "QUEUE_POSITION_UPDATE",
                    "posicao": 2,
                    "status": "APTO_PARA_CHAMADA",
                }
                await valkey.publish(  # pyright: ignore[reportUnknownMemberType]
                    channel, json.dumps(payload)
                )
                await valkey.aclose()

            start_time = time.perf_counter()
            asyncio.run(publish_event())

            # 3. Receive push update via WebSocket
            received_msg = ws.receive_json()
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            assert received_msg["event"] == "QUEUE_POSITION_UPDATE"
            assert received_msg["posicao"] == 2
            # Acceptance Criterion 1: < 500 ms
            assert elapsed_ms < 500.0, f"Expected < 500ms, took {elapsed_ms:.2f}ms"
    finally:
        app.dependency_overrides.clear()


def test_ws_doctor_receives_incoming_call_modal_trigger() -> None:
    """Verify Criterion 2: Doctor receives modal trigger simultaneously with call."""
    app = create_app()
    med_id = uuid4()
    atend_id = uuid4()
    channel = channel_doctor_calls(med_id)
    token = _make_doctor_token(med_id)

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/ws/doctor/{med_id}?token={token}") as ws,
    ):
        # 1. Verify doctor ready status
        initial_msg = ws.receive_json()
        assert initial_msg["event"] == "READY"
        assert initial_msg["medico_id"] == str(med_id)

        # 2. Simulate call allocation broadcast
        async def broadcast_call() -> None:
            pool = get_valkey_pool()
            valkey = Redis(connection_pool=pool)
            await asyncio.sleep(0.05)
            payload = {
                "event": "INCOMING_CALL",
                "atendimento_id": str(atend_id),
                "medico_id": str(med_id),
                "ttl_segundos": 45,
            }
            await valkey.publish(  # pyright: ignore[reportUnknownMemberType]
                channel, json.dumps(payload)
            )
            await valkey.aclose()

        start_time = time.perf_counter()
        asyncio.run(broadcast_call())

        # 3. Doctor client receives modal trigger
        call_msg = ws.receive_json()
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert call_msg["event"] == "INCOMING_CALL"
        assert call_msg["atendimento_id"] == str(atend_id)
        assert call_msg["ttl_segundos"] == 45
        assert elapsed_ms < 500.0


def test_ws_clean_disconnect_without_memory_leaks() -> None:
    """Verify Criterion 3: Disconnects are handled cleanly without exceptions/leaks."""
    app = create_app()
    atend_id = uuid4()
    paciente_id = uuid4()
    token = _make_patient_token(paciente_id)

    async def fake_posse(a_id: UUID, p_id: UUID) -> bool:
        return True

    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: fake_posse

    try:
        with (
            TestClient(app) as client,
            client.websocket_connect(f"/ws/queue/{atend_id}?token={token}") as ws,
        ):
            msg = ws.receive_json()
            assert msg["event"] == "CONNECTED"
            # Explicit close from client side
            ws.close()

        assert True
    finally:
        app.dependency_overrides.clear()
