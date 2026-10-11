"""Integration tests for LiveKit SFU token endpoint and room lifecycle (Issue #42)."""

from typing import cast
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from src.core.authz.roles import Role
from src.core.config import get_settings
from src.core.security import create_intake_token
from src.main import app
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
    AtendimentoResumoDTO,
)
from src.modules.consultation.composition import (
    get_atendimento_reader,
    get_livekit_adapter,
)
from src.modules.consultation.infrastructure.livekit_adapter import (
    FakeLiveKitAdapter,
    LiveKitAdapter,
)

from tests.helpers import auth_headers


class FakeAtendimentoReader(AtendimentoReaderPort):
    def __init__(self, resumo: AtendimentoResumoDTO | None = None) -> None:
        self.resumo = resumo

    async def obter_resumo(self, atendimento_id: UUID) -> AtendimentoResumoDTO | None:
        if self.resumo is not None and self.resumo.atendimento_id == atendimento_id:
            return self.resumo
        return None

    async def concluir_atendimento(self, atendimento_id: UUID) -> None:
        pass


@pytest.mark.asyncio
async def test_livekit_token_endpoint_doctor() -> None:
    """Test generating a room token for an assigned doctor via FastAPI endpoint."""
    atendimento_id = uuid4()
    org_id = 1
    doctor_id = uuid4()
    patient_id = uuid4()

    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atendimento_id,
            organizacao_id=org_id,
            medico_id=doctor_id,
            paciente_id=patient_id,
            status="EM_ATENDIMENTO",
            tcle_hash="a" * 64,
            is_terminal=False,
        )
    )
    app.dependency_overrides[get_atendimento_reader] = lambda: reader

    try:
        payload = {
            "organizacao_id": org_id,
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
                headers=auth_headers(Role.MEDICO, org_id, doctor_id),
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
    finally:
        app.dependency_overrides.pop(get_atendimento_reader, None)


@pytest.mark.asyncio
async def test_livekit_token_endpoint_patient() -> None:
    """Test generating a room token for a patient with intake token."""
    atendimento_id = uuid4()
    org_id = 1
    doctor_id = uuid4()
    patient_id = uuid4()

    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atendimento_id,
            organizacao_id=org_id,
            medico_id=doctor_id,
            paciente_id=patient_id,
            status="EM_ATENDIMENTO",
            tcle_hash="a" * 64,
            is_terminal=False,
        )
    )
    app.dependency_overrides[get_atendimento_reader] = lambda: reader

    settings = get_settings()
    intake_token = create_intake_token(patient_id, org_id, settings.SECRET_KEY)

    try:
        payload = {
            "organizacao_id": org_id,
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
                headers={"Authorization": f"Bearer {intake_token}"},
            )

        assert resp.status_code == 200
        data = cast("dict[str, object]", resp.json())
        assert data["participant_identity"] == f"paciente_{patient_id}"
        assert data["expires_in"] == 1800
    finally:
        app.dependency_overrides.pop(get_atendimento_reader, None)


@pytest.mark.asyncio
async def test_livekit_token_endpoint_anonymous_rejected_401() -> None:
    """Verify anonymous request is rejected with HTTP 401 Unauthorized."""
    atendimento_id = uuid4()
    payload = {
        "organizacao_id": 1,
        "participant_id": str(uuid4()),
        "role": "medico",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/consultations/{atendimento_id}/livekit/token",
            json=payload,
        )
    assert resp.status_code == 401
    assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_livekit_token_endpoint_invalid_token_rejected_401() -> None:
    """Verify malformed token is rejected with HTTP 401 Unauthorized."""
    atendimento_id = uuid4()
    payload = {
        "organizacao_id": 1,
        "participant_id": str(uuid4()),
        "role": "medico",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/consultations/{atendimento_id}/livekit/token",
            json=payload,
            headers={"Authorization": "Bearer invalid.token.payload"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_livekit_token_endpoint_mismatched_doctor_rejected_403() -> None:
    """Verify unassigned doctor is rejected with HTTP 403 Forbidden."""
    atendimento_id = uuid4()
    org_id = 1
    doctor_alocado = uuid4()
    doctor_invasor = uuid4()

    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atendimento_id,
            organizacao_id=org_id,
            medico_id=doctor_alocado,
            paciente_id=uuid4(),
            status="EM_ATENDIMENTO",
            tcle_hash="a" * 64,
            is_terminal=False,
        )
    )
    app.dependency_overrides[get_atendimento_reader] = lambda: reader
    try:
        payload = {
            "organizacao_id": org_id,
            "participant_id": str(doctor_invasor),
            "role": "medico",
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/consultations/{atendimento_id}/livekit/token",
                json=payload,
                headers=auth_headers(Role.MEDICO, org_id, doctor_invasor),
            )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_atendimento_reader, None)


@pytest.mark.asyncio
async def test_livekit_token_endpoint_mismatched_patient_rejected_403() -> None:
    """Verify patient with token for another attendance is rejected with HTTP 403."""
    atendimento_id = uuid4()
    org_id = 1
    paciente_real = uuid4()
    paciente_outro = uuid4()

    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atendimento_id,
            organizacao_id=org_id,
            medico_id=uuid4(),
            paciente_id=paciente_real,
            status="EM_ATENDIMENTO",
            tcle_hash="a" * 64,
            is_terminal=False,
        )
    )
    app.dependency_overrides[get_atendimento_reader] = lambda: reader
    settings = get_settings()
    token_outro = create_intake_token(paciente_outro, org_id, settings.SECRET_KEY)

    try:
        payload = {
            "organizacao_id": org_id,
            "participant_id": str(paciente_outro),
            "role": "paciente",
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/consultations/{atendimento_id}/livekit/token",
                json=payload,
                headers={"Authorization": f"Bearer {token_outro}"},
            )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_atendimento_reader, None)


@pytest.mark.asyncio
async def test_livekit_token_endpoint_terminal_attendance_rejected_403() -> None:
    """Verify concluded attendance rejects token issuance with HTTP 403."""
    atendimento_id = uuid4()
    org_id = 1
    doctor_id = uuid4()

    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atendimento_id,
            organizacao_id=org_id,
            medico_id=doctor_id,
            paciente_id=uuid4(),
            status="CONCLUIDO",
            tcle_hash="a" * 64,
            is_terminal=True,
        )
    )
    app.dependency_overrides[get_atendimento_reader] = lambda: reader
    try:
        payload = {
            "organizacao_id": org_id,
            "participant_id": str(doctor_id),
            "role": "medico",
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/consultations/{atendimento_id}/livekit/token",
                json=payload,
                headers=auth_headers(Role.MEDICO, org_id, doctor_id),
            )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_atendimento_reader, None)


@pytest.mark.asyncio
async def test_livekit_token_endpoint_validation_errors() -> None:
    """Test validation errors on invalid role or invalid TTL."""
    atendimento_id = uuid4()

    # Invalid role
    payload = {
        "organizacao_id": 1,
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
    atendimento_id = uuid4()
    org_id = 1
    patient_id = uuid4()

    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atendimento_id,
            organizacao_id=org_id,
            medico_id=uuid4(),
            paciente_id=patient_id,
            status="EM_ATENDIMENTO",
            tcle_hash="a" * 64,
            is_terminal=False,
        )
    )
    app.dependency_overrides[get_atendimento_reader] = lambda: reader
    settings = get_settings()
    intake_token = create_intake_token(patient_id, org_id, settings.SECRET_KEY)

    try:
        payload = {
            "organizacao_id": org_id,
            "participant_id": str(patient_id),
            "role": "paciente",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/consultations/{atendimento_id}/livekit/token",
                json=payload,
                headers={"Authorization": f"Bearer {intake_token}"},
            )

        assert resp.status_code == 200
        data = cast("dict[str, object]", resp.json())
        assert str(data["token"]).startswith("fake-token-")
        assert len(fake.tokens_issued) == 1
    finally:
        app.dependency_overrides.pop(get_livekit_adapter, None)
        app.dependency_overrides.pop(get_atendimento_reader, None)


@pytest.mark.asyncio
async def test_livekit_sfu_room_lifecycle_twirp() -> None:
    """Test LiveKit SFU room creation, participants listing, and deletion."""
    settings = get_settings()
    adapter = LiveKitAdapter(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        server_url=settings.LIVEKIT_URL,
    )

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
