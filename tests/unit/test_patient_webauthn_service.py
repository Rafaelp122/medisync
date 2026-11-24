"""Unit tests for PatientWebAuthnService (US-14 / FIDO2 / Passkeys)."""

import base64
import hashlib
import json
import struct
from typing import TYPE_CHECKING, cast

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.errors import ConflictError, ForbiddenError, ValidationError
from src.core.security import create_intake_token
from src.core.uuid7 import uuid7
from src.modules.auth.application.dtos import (
    WebAuthnAuthVerifyCommand,
    WebAuthnRegisterVerifyCommand,
)
from src.modules.auth.application.services.patient_webauthn_service import (
    PatientWebAuthnService,
)
from src.modules.auth.domain.exceptions import (
    PasskeyNaoEncontradaError,
    WebAuthnChallengeInvalidoError,
)
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.auth.presentation.dependencies import require_patient_auth
from src.modules.identity.application.ports.identity_reader_port import (
    PacienteAuthLookupData,
)
from src.modules.identity.domain.models.passkey import PacientePasskey
from src.modules.identity.infrastructure.identity_writer_sql import SqlIdentityWriter

from tests.doubles import (
    FakeActiveAttendanceLookup,
    FakeAsyncSession,
    FakeAuditTrail,
    FakeIdentityReader,
    FakeIdentityWriter,
    FakeResult,
    MemoryChallengeStore,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_JWT_SECRET = "test-webauthn-secret-key-min-32-chars-ok"
_RP_ID = "medisync.app"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _encode_client_data(challenge: str, op_type: str) -> str:
    payload = json.dumps(
        {
            "type": op_type,
            "challenge": challenge,
            "origin": "http://localhost:5173",
        }
    ).encode("utf-8")
    return _b64url(payload)


def _generate_es256_keypair() -> tuple[ec.EllipticCurvePrivateKey, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, _b64url(der)


def _build_signed_assertion(
    private_key: ec.EllipticCurvePrivateKey,
    challenge: str,
    *,
    rp_id: str = _RP_ID,
    flags: int = 0x05,
    sign_count: int = 2,
) -> dict[str, object]:
    cdj_b64 = _encode_client_data(challenge, "webauthn.get")
    padded = cdj_b64 + "=" * (-len(cdj_b64) % 4)
    cdj_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
    rp_id_hash = hashlib.sha256(rp_id.encode("utf-8")).digest()
    auth_data = rp_id_hash + bytes([flags]) + struct.pack(">I", sign_count)
    signed_data = auth_data + hashlib.sha256(cdj_bytes).digest()
    signature = private_key.sign(signed_data, ec.ECDSA(hashes.SHA256()))
    return {
        "clientDataJSON": cdj_b64,
        "authenticatorData": _b64url(auth_data),
        "signature": _b64url(signature),
    }


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
    enc = -1 - val
    return bytes([0x20 | enc])


def _build_attestation_object(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    rp_id: str = _RP_ID,
    credential_id: bytes = b"cred-us14-001",
    flags: int = 0x45,
    sign_count: int = 0,
) -> str:
    numbers = private_key.public_key().public_numbers()
    x_bytes = numbers.x.to_bytes(32, "big")
    y_bytes = numbers.y.to_bytes(32, "big")
    cose_key = (
        bytes([0xA5])
        + _cbor_int(1)
        + _cbor_int(2)
        + _cbor_int(3)
        + _cbor_int(-7)
        + _cbor_int(-1)
        + _cbor_int(1)
        + _cbor_int(-2)
        + _cbor_bytes(x_bytes)
        + _cbor_int(-3)
        + _cbor_bytes(y_bytes)
    )
    rp_id_hash = hashlib.sha256(rp_id.encode("utf-8")).digest()
    auth_data = (
        rp_id_hash
        + bytes([flags])
        + struct.pack(">I", sign_count)
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


def _make_service(
    *,
    identity_reader: FakeIdentityReader | None = None,
    identity_writer: FakeIdentityWriter | None = None,
    challenge_store: MemoryChallengeStore | None = None,
    active_attendance: FakeActiveAttendanceLookup | None = None,
    audit_trail: FakeAuditTrail | None = None,
    session: FakeAsyncSession | None = None,
    rp_id: str = _RP_ID,
    allowed_origins: tuple[str, ...] = ("http://localhost:5173",),
) -> PatientWebAuthnService:
    fake_session = session or FakeAsyncSession()
    reader = identity_reader or FakeIdentityReader()
    writer = identity_writer or FakeIdentityWriter(reader)
    return PatientWebAuthnService(
        session=cast("AsyncSession", fake_session),
        token_service=JWTTokenService(
            secret_key=_JWT_SECRET, access_token_expire_minutes=15
        ),
        challenge_store=challenge_store or MemoryChallengeStore(),
        identity_reader=reader,
        identity_writer=writer,
        rp_id=rp_id,
        allowed_origins=allowed_origins,
        active_attendance_lookup=active_attendance,
        audit_trail=audit_trail,
    )


@pytest.mark.asyncio
async def test_gerar_opcoes_registro_usa_dados_paciente_e_persiste_desafio() -> None:
    """Registration options must populate patient displayName and WebAuthn params."""
    paciente_id = uuid7()
    reader = FakeIdentityReader(
        paciente=PacienteAuthLookupData(
            id=paciente_id,
            telefone="11999990000",
            cpf="12345678901",
            nome_completo="Maria da Silva",
        )
    )
    svc = _make_service(identity_reader=reader)

    options = await svc.gerar_opcoes_registro(paciente_id)

    assert len(options.challenge) >= 20
    assert options.rp.id == "medisync.app"
    assert options.user.displayName == "Maria da Silva"
    assert options.attestation == "none"
    assert [param.alg for param in options.pubKeyCredParams] == [-7, -257]


@pytest.mark.asyncio
async def test_verificar_registro_sucesso_persiste_passkey_e_auditoria() -> None:
    """Valid registration challenge stores credential, logs audit and commits once."""
    paciente_id = uuid7()
    reader = FakeIdentityReader(
        paciente=PacienteAuthLookupData(
            id=paciente_id,
            telefone="11999990000",
            cpf="12345678901",
            nome_completo="Maria da Silva",
        )
    )
    audit = FakeAuditTrail()
    session = FakeAsyncSession()
    svc = _make_service(
        identity_reader=reader,
        audit_trail=audit,
        session=session,
    )
    private_key, pub_spki_b64 = _generate_es256_keypair()

    options = await svc.gerar_opcoes_registro(paciente_id)
    assert options.authenticatorSelection.residentKey == "required"
    cmd = WebAuthnRegisterVerifyCommand(
        paciente_id=paciente_id,
        id="cred-us14-001",
        raw_id="cred-us14-001",
        response={
            "clientDataJSON": _encode_client_data(options.challenge, "webauthn.create"),
            "attestationObject": _build_attestation_object(private_key),
        },
        device_name="Android Biometria",
    )

    result = await svc.verificar_registro(cmd)

    assert result.status == "registrado"
    assert result.credencial_id == "cred-us14-001"
    saved = await reader.buscar_passkey_por_credencial("cred-us14-001")
    assert saved is not None
    assert saved.paciente_id == paciente_id
    assert saved.public_key == pub_spki_b64
    assert session.commits == 1
    assert len(audit.get_events_by_type("PASSKEY_REGISTRADA")) == 1


@pytest.mark.asyncio
async def test_verificar_registro_rejeita_replay_e_desafio_divergente() -> None:
    """Missing, replayed, or mismatched registration challenge must fail with 401."""
    paciente_id = uuid7()
    reader = FakeIdentityReader()
    svc = _make_service(identity_reader=reader)
    private_key, pub_spki_b64 = _generate_es256_keypair()

    without_challenge = WebAuthnRegisterVerifyCommand(
        paciente_id=paciente_id,
        id="cred-x",
        raw_id="cred-x",
        response={
            "clientDataJSON": _encode_client_data("no-such", "webauthn.create"),
            "publicKey": pub_spki_b64,
        },
    )
    with pytest.raises(WebAuthnChallengeInvalidoError, match="ausente ou expirado"):
        await svc.verificar_registro(without_challenge)

    options = await svc.gerar_opcoes_registro(paciente_id)
    mismatched = WebAuthnRegisterVerifyCommand(
        paciente_id=paciente_id,
        id="cred-x",
        raw_id="cred-x",
        response={
            "clientDataJSON": _encode_client_data(
                "tampered-challenge", "webauthn.create"
            ),
            "attestationObject": _build_attestation_object(private_key),
        },
    )
    with pytest.raises(WebAuthnChallengeInvalidoError, match="divergente"):
        await svc.verificar_registro(mismatched)

    valid_cmd = WebAuthnRegisterVerifyCommand(
        paciente_id=paciente_id,
        id="cred-x-valid",
        raw_id="cred-x-valid",
        response={
            "clientDataJSON": _encode_client_data(options.challenge, "webauthn.create"),
            "attestationObject": _build_attestation_object(private_key),
        },
    )
    ok = await svc.verificar_registro(valid_cmd)
    assert ok.status == "registrado"

    with pytest.raises(WebAuthnChallengeInvalidoError, match="ausente ou expirado"):
        await svc.verificar_registro(valid_cmd)


@pytest.mark.asyncio
async def test_webauthn_multi_tab_registro_isolado_sem_colisao() -> None:
    """Duas abas simultâneas geram desafios independentes sem sobrescrita."""
    paciente_id = uuid7()
    reader = FakeIdentityReader()
    svc = _make_service(identity_reader=reader)
    k1, _ = _generate_es256_keypair()
    k2, _ = _generate_es256_keypair()

    opt_tab1 = await svc.gerar_opcoes_registro(paciente_id)
    opt_tab2 = await svc.gerar_opcoes_registro(paciente_id)
    assert opt_tab1.challenge != opt_tab2.challenge

    res1 = await svc.verificar_registro(
        WebAuthnRegisterVerifyCommand(
            paciente_id=paciente_id,
            id="cred-tab-1",
            raw_id="cred-tab-1",
            response={
                "clientDataJSON": _encode_client_data(
                    opt_tab1.challenge, "webauthn.create"
                ),
                "attestationObject": _build_attestation_object(k1),
            },
        )
    )
    res2 = await svc.verificar_registro(
        WebAuthnRegisterVerifyCommand(
            paciente_id=paciente_id,
            id="cred-tab-2",
            raw_id="cred-tab-2",
            response={
                "clientDataJSON": _encode_client_data(
                    opt_tab2.challenge, "webauthn.create"
                ),
                "attestationObject": _build_attestation_object(k2),
            },
        )
    )
    assert res1.credencial_id == "cred-tab-1"
    assert res2.credencial_id == "cred-tab-2"


@pytest.mark.asyncio
async def test_verificar_registro_rejeita_client_data_json_sem_challenge() -> None:
    """Registration payload omitting clientDataJSON challenge must be rejected."""
    paciente_id = uuid7()
    reader = FakeIdentityReader()
    svc = _make_service(identity_reader=reader)
    await svc.gerar_opcoes_registro(paciente_id)

    empty_response_cmd = WebAuthnRegisterVerifyCommand(
        paciente_id=paciente_id,
        id="cred-empty",
        raw_id="cred-empty",
        response={},
    )
    with pytest.raises(WebAuthnChallengeInvalidoError, match="divergente"):
        await svc.verificar_registro(empty_response_cmd)


@pytest.mark.asyncio
async def test_autenticacao_passkey_1_toque_emite_jwt_e_atendimento(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1-tap WebAuthn assertion verifies ECDSA signature and updates sign_count."""
    from src.core.config import get_settings

    monkeypatch.setenv("JWT_SECRET_KEY", _JWT_SECRET)
    get_settings.cache_clear()
    try:
        paciente_id = uuid7()
        atendimento_id = uuid7()
        private_key, pub_spki_b64 = _generate_es256_keypair()
        reader = FakeIdentityReader()
        writer = FakeIdentityWriter(reader)
        await writer.registrar_passkey_paciente(
            paciente_id=paciente_id,
            credential_id="cred-1tap-abc",
            public_key=pub_spki_b64,
            sign_count=1,
            device_name="iPhone FaceID",
        )
        active_lookup = FakeActiveAttendanceLookup({paciente_id: atendimento_id})
        audit = FakeAuditTrail()
        session = FakeAsyncSession()
        svc = _make_service(
            identity_reader=reader,
            identity_writer=writer,
            active_attendance=active_lookup,
            audit_trail=audit,
            session=session,
        )

        auth_opts = await svc.gerar_opcoes_autenticacao(paciente_id=paciente_id)
        assert [c.id for c in auth_opts.allowCredentials] == ["cred-1tap-abc"]

        verify_cmd = WebAuthnAuthVerifyCommand(
            id="cred-1tap-abc",
            raw_id="cred-1tap-abc",
            response=_build_signed_assertion(
                private_key,
                auth_opts.challenge,
                sign_count=2,
            ),
        )
        out = await svc.verificar_autenticacao(verify_cmd)

        decoded = decode_access_token(out.access_token)
        assert decoded.usuario_id == paciente_id
        assert not hasattr(decoded, "organizacao_id")
        assert decoded.papel == "PACIENTE"
        assert out.atendimento_id == atendimento_id
        assert out.role == "PACIENTE"
        assert session.commits == 1
        assert len(audit.get_events_by_type("LOGIN_PASSKEY_SUCESSO")) == 1
        updated_pk = await reader.buscar_passkey_por_credencial("cred-1tap-abc")
        assert updated_pk is not None
        assert updated_pk.sign_count == 2
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_autenticacao_passkey_bloqueia_assinatura_ou_sign_count() -> None:
    """Forged signature or non-increasing sign_count raises WebAuthn error."""
    paciente_id = uuid7()
    private_key, pub_spki_b64 = _generate_es256_keypair()
    wrong_private_key, _ = _generate_es256_keypair()
    reader = FakeIdentityReader()
    writer = FakeIdentityWriter(reader)
    await writer.registrar_passkey_paciente(
        paciente_id=paciente_id,
        credential_id="cred-sec-01",
        public_key=pub_spki_b64,
        sign_count=5,
        device_name="Android TouchID",
    )
    svc = _make_service(identity_reader=reader, identity_writer=writer)

    opts1 = await svc.gerar_opcoes_autenticacao(paciente_id)
    forged_cmd = WebAuthnAuthVerifyCommand(
        id="cred-sec-01",
        raw_id="cred-sec-01",
        response=_build_signed_assertion(
            wrong_private_key, opts1.challenge, sign_count=6
        ),
    )
    with pytest.raises(WebAuthnChallengeInvalidoError, match="assinatura"):
        await svc.verificar_autenticacao(forged_cmd)

    opts2 = await svc.gerar_opcoes_autenticacao(paciente_id)
    cloned_cmd = WebAuthnAuthVerifyCommand(
        id="cred-sec-01",
        raw_id="cred-sec-01",
        response=_build_signed_assertion(private_key, opts2.challenge, sign_count=5),
    )
    with pytest.raises(WebAuthnChallengeInvalidoError, match="sign_count"):
        await svc.verificar_autenticacao(cloned_cmd)


@pytest.mark.asyncio
async def test_autenticacao_passkeys_concorrentes_nao_sobrescrevem_desafio() -> None:
    """Two simultaneous authentication ceremonies must both succeed."""
    p1_id = uuid7()
    p2_id = uuid7()
    k1, pub1 = _generate_es256_keypair()
    k2, pub2 = _generate_es256_keypair()
    reader = FakeIdentityReader()
    writer = FakeIdentityWriter(reader)
    await writer.registrar_passkey_paciente(
        paciente_id=p1_id,
        credential_id="cred-p1",
        public_key=pub1,
        sign_count=0,
    )
    await writer.registrar_passkey_paciente(
        paciente_id=p2_id,
        credential_id="cred-p2",
        public_key=pub2,
        sign_count=0,
    )
    svc = _make_service(identity_reader=reader, identity_writer=writer)

    opts_p1 = await svc.gerar_opcoes_autenticacao(p1_id)
    opts_p2 = await svc.gerar_opcoes_autenticacao(p2_id)

    res1 = await svc.verificar_autenticacao(
        WebAuthnAuthVerifyCommand(
            id="cred-p1",
            raw_id="cred-p1",
            response=_build_signed_assertion(k1, opts_p1.challenge, sign_count=1),
        )
    )
    res2 = await svc.verificar_autenticacao(
        WebAuthnAuthVerifyCommand(
            id="cred-p2",
            raw_id="cred-p2",
            response=_build_signed_assertion(k2, opts_p2.challenge, sign_count=1),
        )
    )
    assert res1.paciente_id == p1_id
    assert res2.paciente_id == p2_id


@pytest.mark.asyncio
async def test_autenticacao_passkey_inexistente_rejeitada() -> None:
    """Unknown credential_id must raise PasskeyNaoEncontradaError (401)."""
    reader = FakeIdentityReader()
    svc = _make_service(identity_reader=reader)
    auth_opts = await svc.gerar_opcoes_autenticacao()

    cmd = WebAuthnAuthVerifyCommand(
        id="cred-desconhecida",
        raw_id="cred-desconhecida",
        response={
            "clientDataJSON": _encode_client_data(auth_opts.challenge, "webauthn.get"),
        },
    )

    with pytest.raises(PasskeyNaoEncontradaError, match="cred-desconhecida"):
        await svc.verificar_autenticacao(cmd)


@pytest.mark.asyncio
async def test_webauthn_rejects_wrong_client_data_type_or_origin() -> None:
    """Registration and authentication must enforce clientDataJSON type and origin."""
    paciente_id = uuid7()
    reader = FakeIdentityReader()
    svc = _make_service(
        identity_reader=reader,
        allowed_origins=("https://medisync.app",),
    )
    private_key, _ = _generate_es256_keypair()

    opts_type = await svc.gerar_opcoes_registro(paciente_id)
    wrong_type_cdj = _b64url(
        json.dumps(
            {
                "type": "webauthn.get",
                "challenge": opts_type.challenge,
                "origin": "https://medisync.app",
            }
        ).encode("utf-8")
    )
    with pytest.raises(WebAuthnChallengeInvalidoError, match="type"):
        await svc.verificar_registro(
            WebAuthnRegisterVerifyCommand(
                paciente_id=paciente_id,
                id="cred-bad-type",
                raw_id="cred-bad-type",
                response={
                    "clientDataJSON": wrong_type_cdj,
                    "attestationObject": _build_attestation_object(private_key),
                },
            )
        )

    opts_origin = await svc.gerar_opcoes_registro(paciente_id)
    evil_origin_cdj = _b64url(
        json.dumps(
            {
                "type": "webauthn.create",
                "challenge": opts_origin.challenge,
                "origin": "https://evil-phish.example",
            }
        ).encode("utf-8")
    )
    with pytest.raises(WebAuthnChallengeInvalidoError, match="origin"):
        await svc.verificar_registro(
            WebAuthnRegisterVerifyCommand(
                paciente_id=paciente_id,
                id="cred-bad-origin",
                raw_id="cred-bad-origin",
                response={
                    "clientDataJSON": evil_origin_cdj,
                    "attestationObject": _build_attestation_object(private_key),
                },
            )
        )


@pytest.mark.asyncio
async def test_webauthn_rejects_raw_public_key_without_attestation_object() -> None:
    """Reject registration without CBOR attestationObject even with raw publicKey."""
    paciente_id = uuid7()
    svc = _make_service(identity_reader=FakeIdentityReader())
    _, pub_spki_b64 = _generate_es256_keypair()
    options = await svc.gerar_opcoes_registro(paciente_id)

    with pytest.raises(WebAuthnChallengeInvalidoError, match="attestationObject"):
        await svc.verificar_registro(
            WebAuthnRegisterVerifyCommand(
                paciente_id=paciente_id,
                id="cred-raw-only",
                raw_id="cred-raw-only",
                response={
                    "clientDataJSON": _encode_client_data(
                        options.challenge, "webauthn.create"
                    ),
                    "publicKey": pub_spki_b64,
                },
            )
        )


@pytest.mark.asyncio
async def test_webauthn_rejects_localhost_rpid_when_configured_to_medisync_app() -> (
    None
):
    """Assertion for 'localhost' must fail when service rp_id is 'medisync.app'."""
    paciente_id = uuid7()
    private_key, pub_spki_b64 = _generate_es256_keypair()
    reader = FakeIdentityReader()
    writer = FakeIdentityWriter(reader)
    await writer.registrar_passkey_paciente(
        paciente_id=paciente_id,
        credential_id="cred-prod-rp",
        public_key=pub_spki_b64,
        sign_count=0,
    )
    svc = _make_service(
        identity_reader=reader, identity_writer=writer, rp_id="medisync.app"
    )
    opts = await svc.gerar_opcoes_autenticacao(paciente_id)

    with pytest.raises(WebAuthnChallengeInvalidoError, match="rpIdHash"):
        await svc.verificar_autenticacao(
            WebAuthnAuthVerifyCommand(
                id="cred-prod-rp",
                raw_id="cred-prod-rp",
                response=_build_signed_assertion(
                    private_key,
                    opts.challenge,
                    rp_id="localhost",
                    sign_count=1,
                ),
            )
        )


@pytest.mark.asyncio
async def test_webauthn_challenge_consumed_atomically_via_challenge_store() -> None:
    """ChallengeStorePort consumes challenges atomically to prevent replay."""
    paciente_id = uuid7()
    private_key, _ = _generate_es256_keypair()
    store = MemoryChallengeStore()
    svc = _make_service(identity_reader=FakeIdentityReader(), challenge_store=store)
    opts = await svc.gerar_opcoes_registro(paciente_id)

    cmd = WebAuthnRegisterVerifyCommand(
        paciente_id=paciente_id,
        id="cred-valkey-atomic",
        raw_id="cred-valkey-atomic",
        response={
            "clientDataJSON": _encode_client_data(opts.challenge, "webauthn.create"),
            "attestationObject": _build_attestation_object(private_key),
        },
    )
    result = await svc.verificar_registro(cmd)
    assert result.status == "registrado"
    assert store.consume_calls == [f"webauthn:reg:{paciente_id}:{opts.challenge}"]

    with pytest.raises(WebAuthnChallengeInvalidoError, match="ausente ou expirado"):
        await svc.verificar_registro(cmd)


@pytest.mark.asyncio
async def test_webauthn_register_dependency_accepts_patient_and_rejects_non_patient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PatientAuthDep accepts patient JWT, rejects restricted intake and roles."""
    from fastapi.security import HTTPAuthorizationCredentials
    from src.core.authz.token import create_access_token
    from src.core.config import get_settings

    monkeypatch.setenv("JWT_SECRET_KEY", _JWT_SECRET)
    monkeypatch.setenv("SECRET_KEY", _JWT_SECRET)
    get_settings.cache_clear()
    try:
        paciente_id = uuid7()
        intake_token = create_intake_token(
            paciente_id, _JWT_SECRET, is_novo_paciente=True
        )
        resolved_intake = await require_patient_auth(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=intake_token
            ),
        )
        assert resolved_intake == paciente_id

        restricted_intake = create_intake_token(
            paciente_id, _JWT_SECRET, is_novo_paciente=False
        )
        with pytest.raises(ForbiddenError, match="Token de acolhimento restrito"):
            await require_patient_auth(
                credentials=HTTPAuthorizationCredentials(
                    scheme="Bearer", credentials=restricted_intake
                ),
            )

        jwt_token = create_access_token(
            usuario_id=paciente_id,
            papel=Role.PACIENTE.value,
            secret_key=_JWT_SECRET,
        )
        resolved_jwt = await require_patient_auth(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=jwt_token
            ),
        )
        assert resolved_jwt == paciente_id

        medico_token = create_access_token(
            usuario_id=uuid7(),
            papel=Role.MEDICO.value,
            secret_key=_JWT_SECRET,
        )
        with pytest.raises(ForbiddenError, match="não possui permissão"):
            await require_patient_auth(
                credentials=HTTPAuthorizationCredentials(
                    scheme="Bearer", credentials=medico_token
                ),
            )
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_passkey_model_and_sql_writer_enforce_monotonic_counter() -> None:
    """Enforce monotonic sign_count in model and reject collisions in SQL writer."""
    paciente_id = uuid7()
    passkey = PacientePasskey(
        paciente_id=paciente_id,
        credential_id="cred-mono-01",
        public_key="pub-key-initial",
        sign_count=5,
    )
    with pytest.raises(ValidationError, match=r"sign_count|Contador"):
        passkey.atualizar_contador(5)

    session = FakeAsyncSession(results=[FakeResult(passkey)])
    sql_writer = SqlIdentityWriter(session=cast("AsyncSession", session))
    with pytest.raises(ConflictError, match="já registrada"):
        await sql_writer.registrar_passkey_paciente(
            paciente_id=paciente_id,
            credential_id="cred-mono-01",
            public_key="pub-key-tampered",
            sign_count=6,
        )
