"""Unit tests for LiveKit SFU token generation and naming conventions."""

import time
from uuid import UUID

import jwt
import pytest
from src.modules.consultation.application.ports.livekit_media_port import (
    LiveKitMediaPort,
    build_participant_identity,
    build_room_name,
)
from src.modules.consultation.infrastructure.livekit_adapter import (
    FakeLiveKitAdapter,
    LiveKitAdapter,
)


def test_build_room_name_canonical_format() -> None:
    """Validate canonical room name formatting org_{org_id}_atend_{atend_id}."""
    org_id = UUID("01924b12-9c10-7000-8000-000000000001")
    atend_id = UUID("01924b12-9c10-7000-8000-000000000002")

    room_name = build_room_name(organizacao_id=org_id, atendimento_id=atend_id)
    assert (
        room_name == "org_01924b12-9c10-7000-8000-000000000001"
        "_atend_01924b12-9c10-7000-8000-000000000002"
    )


def test_build_participant_identity_partitioning() -> None:
    """Validate identity partitioning for doctors and patients."""
    user_id = UUID("01924b12-9c10-7000-8000-000000000003")

    doc_identity = build_participant_identity(role="medico", participant_id=user_id)
    assert doc_identity == "medico_01924b12-9c10-7000-8000-000000000003"

    patient_identity = build_participant_identity(
        role="paciente", participant_id=user_id
    )
    assert patient_identity == "paciente_01924b12-9c10-7000-8000-000000000003"


def test_generate_room_token_claims_and_signature() -> None:
    """Validate JWT token claims, signature, and video grant payload."""
    adapter = LiveKitAdapter(
        api_key="test_api_key_12345678901234567890",
        api_secret="test_api_secret_12345678901234567890_min_32_bytes_long",
        server_url="http://localhost:7880",
    )

    room_name = (
        "org_11111111-1111-7000-8000-000000000000"
        "_atend_22222222-2222-7000-8000-000000000000"
    )
    identity = "medico_33333333-3333-7000-8000-000000000000"

    token = adapter.generate_room_token(
        room_name=room_name,
        participant_identity=identity,
        is_publisher=True,
        participant_name="Dra. Alana",
        ttl_seconds=1800,
    )

    assert isinstance(token, str)

    # Decode and verify claims
    decoded: dict[str, object] = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
        token,
        "test_api_secret_12345678901234567890_min_32_bytes_long",
        algorithms=["HS256"],
    )

    assert decoded["iss"] == "test_api_key_12345678901234567890"
    assert decoded["sub"] == identity
    assert decoded["name"] == "Dra. Alana"

    video_grant = decoded.get("video")
    assert isinstance(video_grant, dict)
    assert video_grant["room"] == room_name
    assert video_grant["roomJoin"] is True
    assert video_grant["canPublish"] is True
    assert video_grant["canSubscribe"] is True
    assert video_grant["canPublishData"] is True


def test_generate_room_token_subscriber_only() -> None:
    """Validate token generation for subscriber without publishing grants."""
    adapter = LiveKitAdapter(
        api_key="key",
        api_secret="test_api_secret_12345678901234567890_min_32_bytes_long",
        server_url="http://localhost:7880",
    )

    token = adapter.generate_room_token(
        room_name="room_test",
        participant_identity="paciente_test",
        is_publisher=False,
    )

    decoded: dict[str, object] = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
        token,
        "test_api_secret_12345678901234567890_min_32_bytes_long",
        algorithms=["HS256"],
    )

    video_grant = decoded.get("video")
    assert isinstance(video_grant, dict)
    assert video_grant["roomJoin"] is True
    assert video_grant["canPublish"] is False
    assert video_grant["canSubscribe"] is True


def test_generate_room_token_latency_benchmark() -> None:
    """Verify acceptance criterion: token generation takes < 20ms per token."""
    adapter = LiveKitAdapter(
        api_key="devkey",
        api_secret="devsecret_with_32_characters_for_hmac_sha256",
        server_url="http://localhost:7880",
    )

    iterations = 100
    start = time.perf_counter()
    for _ in range(iterations):
        adapter.generate_room_token(
            room_name="org_1_atend_2",
            participant_identity="medico_1",
            is_publisher=True,
        )
    total_time_ms = (time.perf_counter() - start) * 1000
    avg_latency_ms = total_time_ms / iterations

    # RNF-04 and DoD requirement: < 20 ms
    assert avg_latency_ms < 20.0, f"Token generation too slow: {avg_latency_ms:.4f} ms"
    # In practice it is sub-millisecond (< 1 ms)
    assert avg_latency_ms < 1.0


def test_fake_livekit_adapter_conformance() -> None:
    """Ensure FakeLiveKitAdapter implements LiveKitMediaPort protocol."""
    fake_adapter = FakeLiveKitAdapter()
    assert isinstance(fake_adapter, LiveKitMediaPort)

    token = fake_adapter.generate_room_token(
        room_name="fake_room",
        participant_identity="medico_fake",
        is_publisher=True,
    )
    assert token.startswith("fake-token-")


@pytest.mark.asyncio
async def test_fake_livekit_adapter_lifecycle() -> None:
    """Verify room creation, listing, and deletion on fake adapter."""
    fake = FakeLiveKitAdapter()
    created = await fake.create_room("room-123", empty_timeout=120)
    assert created["name"] == "room-123"
    assert "room-123" in fake.rooms

    participants = await fake.list_participants("room-123")
    assert participants == []

    participants_unknown = await fake.list_participants("unknown-room")
    assert participants_unknown == []

    deleted = await fake.delete_room("room-123")
    assert deleted is True
    assert "room-123" not in fake.rooms

    deleted_again = await fake.delete_room("room-123")
    assert deleted_again is False
