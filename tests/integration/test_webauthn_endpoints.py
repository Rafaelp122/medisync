"""Integration tests for patient FIDO2/WebAuthn passkey routes (US-14 / Issue #115)."""

import base64
import hashlib
import json
import struct
from typing import cast

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.audit import AuditEvent
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.security import create_intake_token
from src.modules.identity.domain.models.passkey import PacientePasskey

from tests.factories.identity import make_paciente
from tests.factories.queue import make_atendimento
from tests.helpers import auth_headers

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _encode_client_data(
    challenge: str, op_type: str, origin: str = "http://localhost:5173"
) -> str:
    payload = json.dumps(
        {
            "type": op_type,
            "challenge": challenge,
            "origin": origin,
        }
    ).encode("utf-8")
    return _b64url(payload)


def _cbor_bytes(data: bytes) -> bytes:
    n = len(data)
    if n < 24:
        return bytes([0x40 | n]) + data
    if n < 256:
        return bytes([0x58, n]) + data
    return bytes([0x59]) + struct.pack(">H", n) + data


def _cbor_text(text: str) -> bytes:
    raw = text.encode("utf-8")
    n = len(raw)
    if n < 24:
        return bytes([0x60 | n]) + raw
    return bytes([0x78, n]) + raw


def _cbor_int(val: int) -> bytes:
    if val >= 0:
        return bytes([val]) if val < 24 else bytes([0x18, val])
    return bytes([0x20 | (-1 - val)])


def _build_attestation_object(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    rp_id: str,
    credential_id: bytes,
) -> str:
    numbers = private_key.public_key().public_numbers()
    cose_key = (
        bytes([0xA5])
        + _cbor_int(1)
        + _cbor_int(2)
        + _cbor_int(3)
        + _cbor_int(-7)
        + _cbor_int(-1)
        + _cbor_int(1)
        + _cbor_int(-2)
        + _cbor_bytes(numbers.x.to_bytes(32, "big"))
        + _cbor_int(-3)
        + _cbor_bytes(numbers.y.to_bytes(32, "big"))
    )
    rp_id_hash = hashlib.sha256(rp_id.encode("utf-8")).digest()
    auth_data = (
        rp_id_hash
        + bytes([0x45])
        + struct.pack(">I", 0)
        + b"\x00" * 16
        + struct.pack(">H", len(credential_id))
        + credential_id
        + cose_key
    )
    att_obj = (
        bytes([0xA3])
        + _cbor_text("fmt")
        + _cbor_text("none")
        + _cbor_text("attStmt")
        + bytes([0xA0])
        + _cbor_text("authData")
        + _cbor_bytes(auth_data)
    )
    return _b64url(att_obj)


def _build_signed_assertion(
    private_key: ec.EllipticCurvePrivateKey,
    challenge: str,
    *,
    rp_id: str,
    sign_count: int = 1,
) -> dict[str, object]:
    cdj_b64 = _encode_client_data(challenge, "webauthn.get")
    padded = cdj_b64 + "=" * (-len(cdj_b64) % 4)
    cdj_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
    rp_id_hash = hashlib.sha256(rp_id.encode("utf-8")).digest()
    auth_data = rp_id_hash + bytes([0x05]) + struct.pack(">I", sign_count)
    signed_data = auth_data + hashlib.sha256(cdj_bytes).digest()
    signature = private_key.sign(signed_data, ec.ECDSA(hashes.SHA256()))
    return {
        "clientDataJSON": cdj_b64,
        "authenticatorData": _b64url(auth_data),
        "signature": _b64url(signature),
    }


@pytest.mark.asyncio
async def test_webauthn_register_and_login_full_lifecycle_with_hmac_and_replay_guard(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate register (HMAC) -> DB/audit -> 1-tap login -> active attendance."""
    paciente = make_paciente(
        cpf="98765432109",
        telefone="11991234567",
        nome_completo="Ana Carolina WebAuthn",
    )
    db_session.add(paciente)
    await db_session.commit()
    await db_session.refresh(paciente)

    atendimento = make_atendimento(
        paciente_id=paciente.id,
        status="APTO_PARA_CHAMADA",
    )
    db_session.add(atendimento)
    await db_session.commit()
    await db_session.refresh(atendimento)

    intake_token = create_intake_token(
        paciente_id=paciente.id,
        secret_key=get_settings().SECRET_KEY,
    )
    patient_headers = {"Authorization": f"Bearer {intake_token}"}

    # 1. Register options via 2-part HMAC intake token
    opt_resp = await async_client.post(
        "/api/v1/auth/patient/webauthn/register/options",
        headers=patient_headers,
    )
    assert opt_resp.status_code == 200
    reg_opts = cast("dict[str, object]", opt_resp.json())
    rp = cast("dict[str, object]", reg_opts["rp"])
    rp_id = str(rp["id"])
    auth_sel = cast("dict[str, object]", reg_opts["authenticatorSelection"])
    assert auth_sel["residentKey"] == "required"
    assert auth_sel["requireResidentKey"] is True

    # 2. Register verify with signed FIDO2 attestationObject
    private_key = ec.generate_private_key(ec.SECP256R1())
    cred_bytes = b"passkey-int-test-001"
    cred_id_b64 = _b64url(cred_bytes)
    verify_reg_resp = await async_client.post(
        "/api/v1/auth/patient/webauthn/register/verify",
        headers=patient_headers,
        json={
            "id": cred_id_b64,
            "rawId": cred_id_b64,
            "type": "public-key",
            "device_name": "Pixel 9 Biometria",
            "response": {
                "clientDataJSON": _encode_client_data(
                    str(reg_opts["challenge"]), "webauthn.create"
                ),
                "attestationObject": _build_attestation_object(
                    private_key, rp_id=rp_id, credential_id=cred_bytes
                ),
            },
        },
    )
    assert verify_reg_resp.status_code == 200
    assert cast("dict[str, object]", verify_reg_resp.json()) == {
        "status": "registrado",
        "credencial_id": cred_id_b64,
    }

    # Verify DB persistence of PacientePasskey and AuditEvent
    db_passkey = (
        await db_session.execute(
            select(PacientePasskey).where(PacientePasskey.credential_id == cred_id_b64)
        )
    ).scalar_one_or_none()
    assert db_passkey is not None
    assert db_passkey.paciente_id == paciente.id
    expected_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert db_passkey.public_key == _b64url(expected_der)

    # 3. Authenticate options (anonymous 1-tap discoverable)
    auth_opt_resp = await async_client.post(
        "/api/v1/auth/patient/webauthn/authenticate/options",
        json={"paciente_id": str(paciente.id)},
    )
    assert auth_opt_resp.status_code == 200
    auth_opts = cast("dict[str, object]", auth_opt_resp.json())
    assert auth_opts["rpId"] == rp_id
    allow_creds = cast("list[dict[str, object]]", auth_opts["allowCredentials"])
    assert len(allow_creds) == 1
    assert allow_creds[0]["id"] == cred_id_b64

    # 4. Authenticate verify -> JWT + atendimento_id
    assertion_payload = {
        "id": cred_id_b64,
        "rawId": cred_id_b64,
        "type": "public-key",
        "response": _build_signed_assertion(
            private_key,
            str(auth_opts["challenge"]),
            rp_id=rp_id,
            sign_count=1,
        ),
    }
    auth_verify_resp = await async_client.post(
        "/api/v1/auth/patient/webauthn/authenticate/verify",
        json=assertion_payload,
    )
    assert auth_verify_resp.status_code == 200
    login_data = cast("dict[str, object]", auth_verify_resp.json())
    assert login_data["role"] == "PACIENTE"
    assert login_data["paciente_id"] == str(paciente.id)
    assert login_data["atendimento_id"] == str(atendimento.id)
    user_claims = decode_access_token(str(login_data["access_token"]))
    assert user_claims.usuario_id == paciente.id

    # 5. Challenge replay must be atomically blocked (GETDEL) -> 401
    replay_resp = await async_client.post(
        "/api/v1/auth/patient/webauthn/authenticate/verify",
        json=assertion_payload,
    )
    assert replay_resp.status_code == 401
    assert (
        cast("dict[str, object]", replay_resp.json())["code"]
        == "WEBAUTHN_CHALLENGE_INVALIDO"
    )

    # 6. Verify PASSKEY_REGISTRADA & LOGIN_PASSKEY_SUCESSO in audit_events
    audit_rows = (
        (
            await db_session.execute(
                select(AuditEvent).where(AuditEvent.ator_id == paciente.id)
            )
        )
        .scalars()
        .all()
    )
    tipos = {row.tipo_evento for row in audit_rows}
    assert "PASSKEY_REGISTRADA" in tipos
    assert "LOGIN_PASSKEY_SUCESSO" in tipos


@pytest.mark.asyncio
async def test_webauthn_register_rbac_and_token_validation(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Reject non-patient roles and missing/tampered tokens on /register/options."""
    paciente = make_paciente(cpf="12312312301")
    db_session.add(paciente)
    await db_session.commit()
    await db_session.refresh(paciente)

    # 1. Missing Authorization header -> 401
    resp_unauth = await async_client.post(
        "/api/v1/auth/patient/webauthn/register/options"
    )
    assert resp_unauth.status_code == 401

    # 2. Corporate non-patient JWT -> 403 Forbidden
    medico_headers = auth_headers("MEDICO", paciente.id)
    resp_forbidden = await async_client.post(
        "/api/v1/auth/patient/webauthn/register/options",
        headers=medico_headers,
    )
    assert resp_forbidden.status_code == 403

    # 3. Valid Patient JWT succeeds -> 200
    jwt_paciente = auth_headers("PACIENTE", paciente.id)
    resp_jwt_ok = await async_client.post(
        "/api/v1/auth/patient/webauthn/register/options",
        headers=jwt_paciente,
    )
    assert resp_jwt_ok.status_code == 200
