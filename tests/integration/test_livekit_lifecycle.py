"""Integration tests for LiveKit SFU token endpoint and room lifecycle."""

from typing import cast
from uuid import uuid4

import httpx
import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from src.core.config import get_settings
from src.main import app
from src.modules.consultation.infrastructure.livekit_adapter import (
    FakeLiveKitAdapter,
    LiveKitAdapter,
    get_livekit_adapter,
)


@pytest.mark.asyncio
async def test_livekit_token_endpoint_doctor() -> None:
    """Test generating a room token for a doctor via FastAPI endpoint."""
    atendimento_id = uuid4()
    org_id = uuid4()
    doctor_id = uuid4()

    payload = {
        "organizacao_id": str(org_id),
        "participant_id": str(doctor_id),
        "role": "medico",
        "participant_name": "Dr. Lucas Ramos",
        "is_publisher": True,
        "ttl_seconds": 3600,
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/consultations/{atendimento_id}/livekit/token",
            json=payload,
        )

    assert resp.status_code == 200
    data = cast("dict[str, object]", resp.json())
    assert "token" in data
    assert data["room_name"] == f"org_{org_id}_atend_{atendimento_id}"
    assert data["participant_identity"] == f"medico_{doctor_id}"
    assert data["expires_in"] == 3600

    # Verify decoded token claims
    settings = get_settings()
    decoded = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
        str(data["token"]),
        settings.LIVEKIT_API_SECRET,
        algorithms=["HS256"],
    )
    assert decoded["sub"] == f"medico_{doctor_id}"
    assert decoded["name"] == "Dr. Lucas Ramos"
    video = cast("dict[str, object]", decoded["video"])
    assert video["room"] == f"org_{org_id}_atend_{atendimento_id}"
    assert video["roomJoin"] is True
    assert video["canPublish"] is True


@pytest.mark.asyncio
async def test_livekit_token_endpoint_patient() -> None:
    """Test generating a room token for a patient via FastAPI endpoint."""
    atendimento_id = uuid4()
    org_id = uuid4()
    patient_id = uuid4()

    payload = {
        "organizacao_id": str(org_id),
        "participant_id": str(patient_id),
        "role": "paciente",
        "participant_name": "Carlos Silva",
        "is_publisher": True,
        "ttl_seconds": 1800,
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/consultations/{atendimento_id}/livekit/token",
            json=payload,
        )

    assert resp.status_code == 200
    data = cast("dict[str, object]", resp.json())
    assert data["participant_identity"] == f"paciente_{patient_id}"
    assert data["expires_in"] == 1800


@pytest.mark.asyncio
async def test_livekit_token_endpoint_validation_errors() -> None:
    """Test validation errors on invalid role or invalid TTL."""
    atendimento_id = uuid4()

    # Invalid role
    payload = {
        "organizacao_id": str(uuid4()),
        "participant_id": str(uuid4()),
        "role": "administrador",  # invalid
        "ttl_seconds": 3600,
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/consultations/{atendimento_id}/livekit/token",
            json=payload,
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_livekit_adapter_dependency_override() -> None:
    """Test replacing LiveKit adapter with fake mock using dependency overrides."""
    fake = FakeLiveKitAdapter()
    app.dependency_overrides[get_livekit_adapter] = lambda: fake
    try:
        atendimento_id = uuid4()
        org_id = uuid4()
        patient_id = uuid4()

        payload = {
            "organizacao_id": str(org_id),
            "participant_id": str(patient_id),
            "role": "paciente",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/consultations/{atendimento_id}/livekit/token",
                json=payload,
            )

        assert resp.status_code == 200
        data = cast("dict[str, object]", resp.json())
        assert str(data["token"]).startswith("fake-token-")
        assert len(fake.tokens_issued) == 1
    finally:
        app.dependency_overrides.pop(get_livekit_adapter, None)


@pytest.mark.asyncio
async def test_livekit_sfu_room_lifecycle_twirp() -> None:
    """Test LiveKit SFU room creation, participants listing, and deletion."""
    settings = get_settings()
    adapter = LiveKitAdapter(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        server_url=settings.LIVEKIT_URL,
    )

    # Check if LiveKit server is reachable
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(settings.LIVEKIT_URL)
            if res.status_code != 200:
                pytest.skip("LiveKit server not running or unhealthy")
    except Exception:
        pytest.skip("LiveKit server not reachable at LIVEKIT_URL")

    test_room_name = f"test_room_{uuid4()}"

    # 1. Create room
    created = await adapter.create_room(
        test_room_name, empty_timeout=60, max_participants=5
    )
    assert created["name"] == test_room_name
    assert "sid" in created

    # 2. List participants (should be empty initially)
    participants = await adapter.list_participants(test_room_name)
    assert isinstance(participants, list)

    # 3. Delete room
    deleted = await adapter.delete_room(test_room_name)
    assert deleted is True
