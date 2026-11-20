"""Integration tests for US-15 Facial Liveness routes and Lista C1 gate."""

from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.audit import AuditEvent
from src.core.authz.roles import Role
from src.core.config import get_settings
from src.core.security import create_intake_token
from src.core.valkey import get_valkey_client

from tests.factories.scenarios import seed_clinical_scenario
from tests.helpers import auth_headers

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_liveness_role_segregation_spoofing_valkey_and_c1_document_gate(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate Medico /challenge, Paciente /verify, Valkey state, audit and C1 gate."""
    cenario = await seed_clinical_scenario(
        db_session,
        unidade_cnpj="77665544000122",
        paciente_cpf="44433322211",
        medico_cpf="55544433322",
        medico_email="dr.liveness@medisync.local",
    )
    atend_id = cenario.atendimento.id

    medico_headers = auth_headers(Role.MEDICO, cenario.medico.id)
    paciente_headers = auth_headers(Role.PACIENTE, cenario.paciente.id)
    intake_token = create_intake_token(
        paciente_id=cenario.paciente.id,
        secret_key=get_settings().SECRET_KEY,
    )
    paciente_intake_headers = {"Authorization": f"Bearer {intake_token}"}

    # 0. Precondition (CFM 2.314/2022): physician verifies identity in SOAP
    soap_resp = await async_client.post(
        f"/api/v1/consultations/{atend_id}/soap",
        headers=medico_headers,
        json={
            "anamnese": "Ansiedade generalizada em acompanhamento.",
            "conduta": "Prescrever Fluoxetina Lista C1 apos prova de vida.",
            "identidade_verificada": True,
            "tipo_documento_verificado": "RG",
        },
    )
    assert soap_resp.status_code == 200

    # 1. C1 document BEFORE liveness must fail with 422 PROVA_DE_VIDA_OBRIGATORIA
    c1_payload = {
        "tipo_documento": "RECEITA_CONTROLE_ESPECIAL_C1",
        "itens": [
            {
                "medicamento": "Fluoxetina 20mg",
                "dosagem": "1 cp",
                "posologia": "1 cp pela manha",
                "duracao": "30 dias",
                "controle_especial": True,
            }
        ],
    }
    blocked_c1 = await async_client.post(
        f"/api/v1/consultations/{atend_id}/documents",
        headers=medico_headers,
        json=c1_payload,
    )
    assert blocked_c1.status_code == 422
    assert (
        cast("dict[str, object]", blocked_c1.json())["code"]
        == "PROVA_DE_VIDA_OBRIGATORIA"
    )

    # 2. Role segregation: Patient cannot request /challenge -> 403
    pac_challenge_denied = await async_client.post(
        f"/api/v1/consultations/{atend_id}/prescriptions/liveness/challenge",
        headers=paciente_headers,
    )
    assert pac_challenge_denied.status_code == 403

    # 3. Role segregation: Physician cannot submit /verify -> 403
    med_verify_denied = await async_client.post(
        f"/api/v1/consultations/{atend_id}/prescriptions/liveness/verify",
        headers=medico_headers,
        json={"challenge_id": "ch_any_value", "liveness_payload": "FRAME_OK"},
    )
    assert med_verify_denied.status_code == 403

    # 4. Physician requests liveness challenge -> persisted in Valkey
    ch_resp = await async_client.post(
        f"/api/v1/consultations/{atend_id}/prescriptions/liveness/challenge",
        headers=medico_headers,
    )
    assert ch_resp.status_code == 200
    ch_data = cast("dict[str, object]", ch_resp.json())
    ch_id = str(ch_data["challenge_id"])

    async for valkey in get_valkey_client():
        raw_val = await valkey.get(f"liveness:challenge:{ch_id}")  # pyright: ignore[reportUnknownMemberType]
        assert raw_val == str(atend_id)

    # 5. Spoofing attempt by Patient -> 422 SPOOFING_FACIAL_DETECTADO + audit event
    spoof_resp = await async_client.post(
        f"/api/v1/consultations/{atend_id}/prescriptions/liveness/verify",
        headers=paciente_headers,
        json={
            "challenge_id": ch_id,
            "liveness_payload": "SPOOF_STATIC_PHOTO_FRAME",
        },
    )
    assert spoof_resp.status_code == 422
    assert (
        cast("dict[str, object]", spoof_resp.json())["code"]
        == "SPOOFING_FACIAL_DETECTADO"
    )

    # 6. Replay consumed challenge -> 422 LIVENESS_CHALLENGE_INVALIDO (no spoofing log)
    replay_resp = await async_client.post(
        f"/api/v1/consultations/{atend_id}/prescriptions/liveness/verify",
        headers=paciente_headers,
        json={"challenge_id": ch_id, "liveness_payload": "LIVE_FRAMES_OK"},
    )
    assert replay_resp.status_code == 422
    assert (
        cast("dict[str, object]", replay_resp.json())["code"]
        == "LIVENESS_CHALLENGE_INVALIDO"
    )

    # 7. Happy path: Physician requests challenge, Patient verifies via intake token
    ch_resp_2 = await async_client.post(
        f"/api/v1/consultations/{atend_id}/prescriptions/liveness/challenge",
        headers=medico_headers,
    )
    assert ch_resp_2.status_code == 200
    ch_id_2 = str(cast("dict[str, object]", ch_resp_2.json())["challenge_id"])

    verify_ok = await async_client.post(
        f"/api/v1/consultations/{atend_id}/prescriptions/liveness/verify",
        headers=paciente_intake_headers,
        json={
            "challenge_id": ch_id_2,
            "liveness_payload": "data:image/jpeg;base64,/9j/LIVE_FRAMES_OK",
            "geolocalizacao": {"latitude": -23.5505, "longitude": -46.6333},
        },
    )
    assert verify_ok.status_code == 200
    verify_data = cast("dict[str, object]", verify_ok.json())
    assert verify_data["status"] == "APROVADO"
    liveness_hash = str(verify_data["verificacao_hash"])

    async for valkey in get_valkey_client():
        approved_val = await valkey.get(f"liveness:approved:{atend_id}")  # pyright: ignore[reportUnknownMemberType]
        assert approved_val == liveness_hash

    # 8. Now Lista C1 emission succeeds with approved hash
    emit_c1_ok = await async_client.post(
        f"/api/v1/consultations/{atend_id}/documents",
        headers=medico_headers,
        json={**c1_payload, "liveness_verificacao_hash": liveness_hash},
    )
    assert emit_c1_ok.status_code == 201
    doc_data = cast("dict[str, object]", emit_c1_ok.json())
    assert doc_data["liveness_verificacao_hash"] == liveness_hash

    # Verify audit trail events in Postgres
    events = (
        (
            await db_session.execute(
                select(AuditEvent).where(AuditEvent.atendimento_id == atend_id)
            )
        )
        .scalars()
        .all()
    )
    spoof_events = [e for e in events if e.tipo_evento == "SPOOFING_FACIAL_DETECTADO"]
    approved_events = [e for e in events if e.tipo_evento == "LIVENESS_FACIAL_APROVADO"]
    assert len(spoof_events) == 1
    assert len(approved_events) == 1
