"""Unit tests for PatientWebAuthnService (US-14 / FIDO2 / Passkeys)."""

import base64
import json
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from src.core.authz.token import decode_access_token
from src.core.uuid7 import uuid7
from src.modules.auth.application.dtos import (
    WebAuthnAuthVerifyCommand,
    WebAuthnRegisterVerifyCommand,
)
from src.modules.auth.application.ports.active_attendance_lookup_port import (
    ActiveAttendanceLookupPort,
)
from src.modules.auth.application.services.patient_webauthn_service import (
    PatientWebAuthnService,
)
from src.modules.auth.domain.exceptions import (
    PasskeyNaoEncontradaError,
    WebAuthnChallengeInvalidoError,
)
from src.modules.identity.application.ports.identity_reader_port import (
    PacienteAuthLookupData,
)

from tests.doubles import FakeAsyncSession, FakeAuditTrail, FakeIdentityReader

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_JWT_SECRET = "test-webauthn-secret-key-min-32-chars-ok"
_ORG_ID = 1


class FakeActiveAttendanceLookup(ActiveAttendanceLookupPort):
    """Named in-memory double implementing ActiveAttendanceLookupPort."""

    def __init__(self, active_map: dict[tuple[int, UUID], UUID] | None = None) -> None:
        self._active_map = dict(active_map or {})

    async def buscar_atendimento_ativo_paciente(
        self,
        organizacao_id: int,
        paciente_id: UUID,
    ) -> UUID | None:
        return self._active_map.get((organizacao_id, paciente_id))


def _encode_client_data(challenge: str, op_type: str) -> str:
    payload = json.dumps(
        {
            "type": op_type,
            "challenge": challenge,
            "origin": "http://localhost:5173",
        }
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _make_service(
    *,
    identity_reader: FakeIdentityReader | None = None,
    active_attendance: FakeActiveAttendanceLookup | None = None,
    audit_trail: FakeAuditTrail | None = None,
    session: FakeAsyncSession | None = None,
) -> PatientWebAuthnService:
    fake_session = session or FakeAsyncSession()
    return PatientWebAuthnService(
        jwt_secret=_JWT_SECRET,
        identity_reader=identity_reader,
        active_attendance_lookup=active_attendance,
        audit_trail=audit_trail,
        session=cast("AsyncSession", fake_session),
    )


@pytest.mark.asyncio
async def test_gerar_opcoes_registro_usa_dados_paciente_e_persiste_desafio() -> None:
    """Registration options must populate patient displayName and WebAuthn params."""
    paciente_id = uuid7()
    reader = FakeIdentityReader(
        paciente=PacienteAuthLookupData(
            id=paciente_id,
            organizacao_id=_ORG_ID,
            telefone="11999990000",
            cpf="12345678901",
            nome_completo="Maria da Silva",
        )
    )
    svc = _make_service(identity_reader=reader)

    options = await svc.gerar_opcoes_registro(_ORG_ID, paciente_id)

    assert len(options.challenge) >= 20
    assert options.rp.id == "medisync.app"
    assert options.user.displayName == "Maria da Silva"
    assert options.attestation == "none"
    assert [param.alg for param in options.pubKeyCredParams] == [-7, -257]


@pytest.mark.asyncio
async def test_verificar_registro_sucesso_persiste_passkey_e_auditoria() -> None:
    """Valid registration challenge stores credential and logs PASSKEY_REGISTRADA."""
    paciente_id = uuid7()
    reader = FakeIdentityReader(
        paciente=PacienteAuthLookupData(
            id=paciente_id,
            organizacao_id=_ORG_ID,
            telefone="11999990000",
            cpf="12345678901",
            nome_completo="Maria da Silva",
        )
    )
    audit = FakeAuditTrail()
    svc = _make_service(identity_reader=reader, audit_trail=audit)

    options = await svc.gerar_opcoes_registro(_ORG_ID, paciente_id)
    cmd = WebAuthnRegisterVerifyCommand(
        organizacao_id=_ORG_ID,
        paciente_id=paciente_id,
        id="cred-us14-001",
        raw_id="cred-us14-001",
        response={
            "clientDataJSON": _encode_client_data(options.challenge, "webauthn.create"),
            "publicKey": "COSE_KEY_DATA_BASE64",
        },
        device_name="Android Biometria",
    )

    result = await svc.verificar_registro(cmd)

    assert result.status == "registrado"
    assert result.credencial_id == "cred-us14-001"
    saved = await reader.buscar_passkey_por_credencial(_ORG_ID, "cred-us14-001")
    assert saved is not None
    assert saved.paciente_id == paciente_id
    assert saved.public_key == "COSE_KEY_DATA_BASE64"
    assert len(audit.get_events_by_type("PASSKEY_REGISTRADA")) == 1


@pytest.mark.asyncio
async def test_verificar_registro_rejeita_replay_e_desafio_divergente() -> None:
    """Missing, replayed, or mismatched registration challenge must fail with 401."""
    paciente_id = uuid7()
    reader = FakeIdentityReader()
    svc = _make_service(identity_reader=reader)

    without_challenge = WebAuthnRegisterVerifyCommand(
        organizacao_id=_ORG_ID,
        paciente_id=paciente_id,
        id="cred-x",
        raw_id="cred-x",
        response={"clientDataJSON": _encode_client_data("no-such", "webauthn.create")},
    )
    with pytest.raises(WebAuthnChallengeInvalidoError, match="ausente ou expirado"):
        await svc.verificar_registro(without_challenge)

    options = await svc.gerar_opcoes_registro(_ORG_ID, paciente_id)
    mismatched = WebAuthnRegisterVerifyCommand(
        organizacao_id=_ORG_ID,
        paciente_id=paciente_id,
        id="cred-x",
        raw_id="cred-x",
        response={
            "clientDataJSON": _encode_client_data(
                "tampered-challenge", "webauthn.create"
            )
        },
    )
    with pytest.raises(WebAuthnChallengeInvalidoError, match="divergente"):
        await svc.verificar_registro(mismatched)

    # Challenge was consumed once; replaying with original challenge must also fail.
    replay = WebAuthnRegisterVerifyCommand(
        organizacao_id=_ORG_ID,
        paciente_id=paciente_id,
        id="cred-x",
        raw_id="cred-x",
        response={
            "clientDataJSON": _encode_client_data(options.challenge, "webauthn.create")
        },
    )
    with pytest.raises(WebAuthnChallengeInvalidoError, match="ausente ou expirado"):
        await svc.verificar_registro(replay)


@pytest.mark.asyncio
async def test_autenticacao_passkey_1_toque_emite_jwt_e_atendimento(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1-tap WebAuthn assertion emits Role.PACIENTE JWT and resolves active queue."""
    from src.core.config import get_settings

    monkeypatch.setenv("JWT_SECRET_KEY", _JWT_SECRET)
    get_settings.cache_clear()
    try:
        paciente_id = uuid7()
        atendimento_id = uuid7()
        reader = FakeIdentityReader()
        await reader.registrar_passkey_paciente(
            organizacao_id=_ORG_ID,
            paciente_id=paciente_id,
            credential_id="cred-1tap-abc",
            public_key="PUBKEY_PEM_SIM",
            sign_count=1,
            device_name="iPhone FaceID",
        )
        active_lookup = FakeActiveAttendanceLookup(
            {(_ORG_ID, paciente_id): atendimento_id}
        )
        audit = FakeAuditTrail()
        session = FakeAsyncSession()
        svc = _make_service(
            identity_reader=reader,
            active_attendance=active_lookup,
            audit_trail=audit,
            session=session,
        )

        auth_opts = await svc.gerar_opcoes_autenticacao(
            organizacao_id=_ORG_ID,
            paciente_id=paciente_id,
        )
        assert [c.id for c in auth_opts.allowCredentials] == ["cred-1tap-abc"]

        verify_cmd = WebAuthnAuthVerifyCommand(
            organizacao_id=_ORG_ID,
            id="cred-1tap-abc",
            raw_id="cred-1tap-abc",
            response={
                "clientDataJSON": _encode_client_data(
                    auth_opts.challenge, "webauthn.get"
                ),
                "authenticatorData": "AUTH_DATA",
                "signature": "SIG_BYTES",
            },
        )
        out = await svc.verificar_autenticacao(verify_cmd)

        decoded = decode_access_token(out.access_token)
        assert decoded.usuario_id == paciente_id
        assert decoded.organizacao_id == _ORG_ID
        assert decoded.papel == "PACIENTE"
        assert out.atendimento_id == atendimento_id
        assert out.role == "PACIENTE"
        assert session.commits == 1
        assert len(audit.get_events_by_type("LOGIN_PASSKEY_SUCESSO")) == 1
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_autenticacao_passkey_inexistente_rejeitada() -> None:
    """Unknown credential_id must raise PasskeyNaoEncontradaError (401)."""
    reader = FakeIdentityReader()
    svc = _make_service(identity_reader=reader)
    auth_opts = await svc.gerar_opcoes_autenticacao(_ORG_ID)

    cmd = WebAuthnAuthVerifyCommand(
        organizacao_id=_ORG_ID,
        id="cred-desconhecida",
        raw_id="cred-desconhecida",
        response={
            "clientDataJSON": _encode_client_data(auth_opts.challenge, "webauthn.get"),
        },
    )

    with pytest.raises(PasskeyNaoEncontradaError, match="cred-desconhecida"):
        await svc.verificar_autenticacao(cmd)
