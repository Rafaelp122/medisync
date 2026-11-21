"""Integration tests for patient passwordless OTP authentication endpoints."""

import hashlib
from datetime import date
from typing import TYPE_CHECKING, cast

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import DevelopmentSettings
from src.core.database import get_session_factory
from src.core.errors import ConflictError
from src.core.valkey import get_valkey_pool
from src.modules.auth.application.dtos import RegistrarPacienteCommand
from src.modules.auth.composition import build_patient_auth_service_for_session
from src.modules.auth.domain.models import UsuarioCredencial
from src.modules.auth.infrastructure.patient_credential_repository_sql import (
    SqlPatientCredentialRepository,
)
from src.modules.identity.composition import get_sms_sender
from src.modules.identity.domain.models import Paciente

if TYPE_CHECKING:
    from src.modules.identity.infrastructure.fake_sms_adapter import (
        FakeSmsSenderAdapter,
    )

from tests.factories.identity import make_paciente

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_patient_otp_lifecycle_e2e(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate full passwordless OTP lifecycle: request, receive, verify, issue JWT."""
    paciente = make_paciente(
        cpf="11144477735",
        telefone="11987654321",
        nome_completo="Juliana Silva",
    )
    db_session.add(paciente)
    await db_session.commit()
    await db_session.refresh(paciente)

    fake_sms = cast("FakeSmsSenderAdapter", get_sms_sender())
    fake_sms.clear()

    # 2. Request OTP
    req_resp = await async_client.post(
        "/api/v1/auth/patient/otp/request",
        json={"telefone": "11987654321"},
    )
    assert req_resp.status_code == 200
    req_data = cast("dict[str, object]", req_resp.json())
    assert req_data["mensagem"] == "Código de verificação enviado com sucesso."
    assert req_data["expira_em_segundos"] == 300

    assert len(fake_sms.sent_otps) == 1
    otp_code = fake_sms.sent_otps[0]["codigo"]
    assert len(otp_code) == 6

    # 3. Verify OTP
    verify_resp = await async_client.post(
        "/api/v1/auth/patient/otp/verify",
        json={"telefone": "11987654321", "codigo": otp_code},
    )
    assert verify_resp.status_code == 200
    verify_data = cast("dict[str, object]", verify_resp.json())
    assert "access_token" in verify_data
    assert verify_data["token_type"] == "bearer"
    assert verify_data["paciente_id"] == str(paciente.id)
    assert verify_data["role"] == "PACIENTE"

    # 4. Validate JWT Token claims and role
    token = cast("str", verify_data["access_token"])
    user = decode_access_token(token)
    assert user.usuario_id == paciente.id
    assert user.papel == Role.PACIENTE.value
    assert user.has_permission("patient:queue_track")
    assert user.has_permission("patient:doc_view")


@pytest.mark.asyncio
async def test_patient_otp_paciente_nao_encontrado_retorna_neutro_200(
    async_client: AsyncClient,
) -> None:
    """Validate neutral 200 OK response when phone is unregistered."""
    fake_sms = cast("FakeSmsSenderAdapter", get_sms_sender())
    fake_sms.clear()

    resp = await async_client.post(
        "/api/v1/auth/patient/otp/request",
        json={"telefone": "11999998888"},
    )
    assert resp.status_code == 200
    data = cast("dict[str, object]", resp.json())
    assert data["mensagem"] == "Código de verificação enviado com sucesso."
    assert data["expira_em_segundos"] == 300
    assert data["codigo_debug"] is None
    assert len(fake_sms.sent_otps) == 0


@pytest.mark.asyncio
async def test_patient_otp_rate_limiting_retorna_429(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate 429 Too Many Requests after 3 OTP requests in sliding window."""
    paciente = make_paciente(
        cpf="11144477735",
        telefone="11987654322",
    )
    db_session.add(paciente)
    await db_session.commit()

    for _ in range(3):
        r = await async_client.post(
            "/api/v1/auth/patient/otp/request",
            json={"telefone": "11987654322"},
        )
        assert r.status_code == 200

    # 4th request must be rate-limited
    r_limited = await async_client.post(
        "/api/v1/auth/patient/otp/request",
        json={"telefone": "11987654322"},
    )
    assert r_limited.status_code == 429
    err_data = cast("dict[str, object]", r_limited.json())
    assert err_data["code"] == "OTP_RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_patient_otp_codigo_errado_retorna_401(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate 401 Unauthorized when OTP code is incorrect."""
    paciente = make_paciente(
        cpf="11144477735",
        telefone="11987654323",
    )
    db_session.add(paciente)
    await db_session.commit()

    await async_client.post(
        "/api/v1/auth/patient/otp/request",
        json={"telefone": "11987654323"},
    )

    verify_resp = await async_client.post(
        "/api/v1/auth/patient/otp/verify",
        json={"telefone": "11987654323", "codigo": "000000"},
    )
    assert verify_resp.status_code == 401
    err_data = cast("dict[str, object]", verify_resp.json())
    assert err_data["code"] == "OTP_INVALIDO"


@pytest.mark.asyncio
async def test_patient_otp_bloqueio_3_tentativas_retorna_429_com_retry_after(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate that 3 failed OTP verify attempts trigger 429 with Retry-After: 900."""
    paciente = make_paciente(
        cpf="11144477735",
        telefone="11987654324",
    )
    db_session.add(paciente)
    await db_session.commit()

    fake_sms = cast("FakeSmsSenderAdapter", get_sms_sender())
    fake_sms.clear()

    req_resp = await async_client.post(
        "/api/v1/auth/patient/otp/request",
        json={"telefone": "11987654324"},
    )
    assert req_resp.status_code == 200
    codigo_valido = fake_sms.sent_otps[0]["codigo"]

    # Tentativa 1 incorreta -> 401
    resp1 = await async_client.post(
        "/api/v1/auth/patient/otp/verify",
        json={"telefone": "11987654324", "codigo": "000000"},
    )
    assert resp1.status_code == 401
    assert "Restam 2 tentativa(s)" in resp1.json()["detail"]

    # Tentativa 2 incorreta -> 401
    resp2 = await async_client.post(
        "/api/v1/auth/patient/otp/verify",
        json={"telefone": "11987654324", "codigo": "000000"},
    )
    assert resp2.status_code == 401
    assert "Restam 1 tentativa(s)" in resp2.json()["detail"]

    # Tentativa 3 incorreta -> 429 Too Many Requests com Retry-After: 900
    resp3 = await async_client.post(
        "/api/v1/auth/patient/otp/verify",
        json={"telefone": "11987654324", "codigo": "000000"},
    )
    assert resp3.status_code == 429
    assert resp3.headers.get("retry-after") == "900"
    data3 = cast("dict[str, object]", resp3.json())
    assert data3["code"] == "OTP_TENTATIVAS_EXCEDIDAS"
    assert "1198****4324" in cast("str", data3["detail"])

    # Tentativa 4, mesmo com código correto -> 401 (OTP expurgado)
    resp4 = await async_client.post(
        "/api/v1/auth/patient/otp/verify",
        json={"telefone": "11987654324", "codigo": codigo_valido},
    )
    assert resp4.status_code == 401


@pytest.mark.asyncio
async def test_patient_hybrid_register_identify_password_and_methods_e2e(
    async_client: AsyncClient,
) -> None:
    """Validate register, identify, password login, and methods endpoints E2E."""
    fake_sms = cast("FakeSmsSenderAdapter", get_sms_sender())
    fake_sms.clear()

    # 1. GET /auth/patient/methods
    methods_resp = await async_client.get("/api/v1/auth/patient/methods")
    assert methods_resp.status_code == 200
    methods_data = cast("dict[str, object]", methods_resp.json())
    assert methods_data == {
        "govbr_oidc_enabled": False,
        "passkeys_enabled": True,
        "otp_enabled": True,
        "password_fallback_enabled": True,
    }

    # 2. POST /auth/patient/register with email + senha
    reg_payload = {
        "cpf": "111.444.777-35",
        "nome_completo": "Marina Costa",
        "data_nascimento": "1993-06-12",
        "telefone": "11987654325",
        "aceite_privacidade": True,
        "email": "Marina.Costa@example.com",
        "senha": "SenhaPaciente123",
    }
    reg_resp = await async_client.post(
        "/api/v1/auth/patient/register",
        json=reg_payload,
    )
    assert reg_resp.status_code == 201
    reg_data = cast("dict[str, object]", reg_resp.json())
    paciente_id = cast("str", reg_data["paciente_id"])
    assert reg_data["telefone_mascarado"] == "1198****4325"
    assert reg_data["otp_enviado"] is True
    assert reg_data["expira_em_segundos"] == 300
    assert len(fake_sms.sent_otps) == 1

    # Duplicate CPF returns 409 Conflict without leaking CPF
    dup_resp = await async_client.post(
        "/api/v1/auth/patient/register",
        json={**reg_payload, "email": "outra.marina@example.com"},
    )
    assert dup_resp.status_code == 409
    dup_data = cast("dict[str, object]", dup_resp.json())
    dup_detail = cast("str", dup_data["detail"])
    assert "11144477735" not in dup_detail
    assert "111.***.***-35" not in dup_detail
    assert "organização" not in dup_detail.lower()
    assert "entrar" in dup_detail.lower()

    # 3. POST /auth/patient/identify (CPF, email, and absent CPF)
    id_cpf_resp = await async_client.post(
        "/api/v1/auth/patient/identify",
        json={"identificador": "11144477735"},
    )
    assert id_cpf_resp.status_code == 200
    id_cpf_data = cast("dict[str, object]", id_cpf_resp.json())
    assert id_cpf_data["possui_conta"] is True
    assert id_cpf_data["telefone_mascarado"] == "1198****4325"
    metodos = set(cast("list[str]", id_cpf_data["metodos_disponiveis"]))
    assert metodos == {"otp", "senha"}
    assert "Marina" not in str(id_cpf_data)
    assert "11144477735" not in str(id_cpf_data)
    assert "11987654325" not in str(id_cpf_data)

    id_email_resp = await async_client.post(
        "/api/v1/auth/patient/identify",
        json={"identificador": "marina.costa@example.com"},
    )
    assert id_email_resp.status_code == 200
    assert id_email_resp.json()["possui_conta"] is True

    id_missing_resp = await async_client.post(
        "/api/v1/auth/patient/identify",
        json={"identificador": "52998224725"},
    )
    assert id_missing_resp.status_code == 200
    assert id_missing_resp.json() == {
        "possui_conta": False,
        "metodos_disponiveis": [],
        "telefone_mascarado": None,
        "govbr_habilitado": False,
    }

    # 4. POST /auth/patient/login-password (no MFA required)
    login_resp = await async_client.post(
        "/api/v1/auth/patient/login-password",
        json={
            "identificador": "marina.costa@example.com",
            "senha": "SenhaPaciente123",
        },
    )
    assert login_resp.status_code == 200
    login_data = cast("dict[str, object]", login_resp.json())
    assert login_data["paciente_id"] == paciente_id
    assert login_data["role"] == "PACIENTE"
    token = cast("str", login_data["access_token"])
    claims = decode_access_token(token)
    assert str(claims.usuario_id) == paciente_id
    assert claims.papel == Role.PACIENTE.value

    # 5 wrong attempts trigger 423 Locked
    for _ in range(4):
        fail_resp = await async_client.post(
            "/api/v1/auth/patient/login-password",
            json={
                "identificador": "marina.costa@example.com",
                "senha": "WrongPassword",
            },
        )
        assert fail_resp.status_code == 401

    locked_resp = await async_client.post(
        "/api/v1/auth/patient/login-password",
        json={"identificador": "marina.costa@example.com", "senha": "WrongPassword"},
    )
    assert locked_resp.status_code == 423


@pytest.mark.asyncio
async def test_patient_register_email_conflict_atomic_rollback(
    async_client: AsyncClient,
) -> None:
    """Verify duplicate email returns 409 and leaves zero orphan Paciente rows."""
    first_resp = await async_client.post(
        "/api/v1/auth/patient/register",
        json={
            "cpf": "11144477735",
            "nome_completo": "Primeiro Paciente",
            "data_nascimento": "1990-01-10",
            "telefone": "11987654326",
            "aceite_privacidade": True,
            "email": "duplicado@example.com",
            "senha": "SenhaForte123",
        },
    )
    assert first_resp.status_code == 201

    # Second patient with distinct CPF but duplicate email (case-insensitive)
    dup_resp = await async_client.post(
        "/api/v1/auth/patient/register",
        json={
            "cpf": "52998224725",
            "nome_completo": "Segundo Paciente",
            "data_nascimento": "1991-02-20",
            "telefone": "11987654327",
            "aceite_privacidade": True,
            "email": "DUPLICADO@example.com",
            "senha": "OutraSenha123",
        },
    )
    assert dup_resp.status_code == 409

    # Bypass pre-check to prove Postgres atomic rollback even after Paciente flush
    class _RaceBypassCredentialRepo(SqlPatientCredentialRepository):
        async def existe_identificador(self, identificador: str) -> bool:
            return False

    async with get_session_factory()() as race_session:
        service = build_patient_auth_service_for_session(
            session=race_session,
            credential_repo=_RaceBypassCredentialRepo(session=race_session),
        )
        with pytest.raises(ConflictError):
            await service.registrar_paciente(
                RegistrarPacienteCommand(
                    cpf="71428793860",
                    nome_completo="Terceiro Corrida",
                    data_nascimento=date(1992, 3, 15),
                    telefone="11987654328",
                    email="duplicado@example.com",
                    aceite_privacidade=True,
                    senha="SenhaCorrida123",
                )
            )
        await race_session.rollback()

    async with get_session_factory()() as check_session:
        pacientes = (await check_session.execute(select(Paciente))).scalars().all()
        creds = (await check_session.execute(select(UsuarioCredencial))).scalars().all()
        assert len(pacientes) == 1
        assert pacientes[0].cpf == "11144477735"
        assert len(creds) == 1


@pytest.mark.asyncio
async def test_patient_login_password_with_cpf_and_corporate_login_rejects_paciente(
    async_client: AsyncClient,
) -> None:
    """Validate /patient/login-password accepts CPF and /auth/login rejects PACIENTE."""
    reg_resp = await async_client.post(
        "/api/v1/auth/patient/register",
        json={
            "cpf": "111.444.777-35",
            "nome_completo": "Paciente CPF",
            "data_nascimento": "1989-08-14",
            "telefone": "11987654330",
            "aceite_privacidade": True,
            "email": "paciente.cpf@example.com",
            "senha": "SenhaPaciente123",
        },
    )
    assert reg_resp.status_code == 201
    paciente_id = cast("str", reg_resp.json()["paciente_id"])

    # Login via formatted CPF
    cpf_login = await async_client.post(
        "/api/v1/auth/patient/login-password",
        json={"identificador": "111.444.777-35", "senha": "SenhaPaciente123"},
    )
    assert cpf_login.status_code == 200
    login_data = cast("dict[str, object]", cpf_login.json())
    assert login_data["paciente_id"] == paciente_id
    assert login_data["role"] == "PACIENTE"
    claims = decode_access_token(cast("str", login_data["access_token"]))
    assert claims.papel == Role.PACIENTE.value
    assert str(claims.usuario_id) == paciente_id

    # Corporate login /auth/login MUST reject PACIENTE credential with 401
    corp_login = await async_client.post(
        "/api/v1/auth/login",
        json={"identificador": "paciente.cpf@example.com", "senha": "SenhaPaciente123"},
    )
    assert corp_login.status_code == 401
    assert (
        cast("dict[str, object]", corp_login.json())["code"] == "CREDENCIAIS_INVALIDAS"
    )


@pytest.mark.asyncio
async def test_patient_auth_cross_phone_otp_and_credential_isolation(
    async_client: AsyncClient,
) -> None:
    """Validate OTP isolation between two patients and credential mismatch rejection."""
    fake_sms = cast("FakeSmsSenderAdapter", get_sms_sender())
    fake_sms.clear()

    reg_a = await async_client.post(
        "/api/v1/auth/patient/register",
        json={
            "cpf": "11144477735",
            "nome_completo": "Paciente A",
            "data_nascimento": "1991-04-05",
            "telefone": "11987654331",
            "aceite_privacidade": True,
            "email": "paciente_a@example.com",
            "senha": "SenhaPacienteA123",
        },
    )
    assert reg_a.status_code == 201
    assert len(fake_sms.sent_otps) == 1
    otp_a = fake_sms.sent_otps[0]["codigo"]

    reg_b = await async_client.post(
        "/api/v1/auth/patient/register",
        json={
            "cpf": "52998224725",
            "nome_completo": "Paciente B",
            "data_nascimento": "1992-07-19",
            "telefone": "11987654339",
            "aceite_privacidade": True,
            "email": "paciente_b@example.com",
            "senha": "SenhaPacienteB123",
        },
    )
    assert reg_b.status_code == 201

    # Patient A password against Patient B email rejects with 401
    pwd_cross = await async_client.post(
        "/api/v1/auth/patient/login-password",
        json={"identificador": "paciente_b@example.com", "senha": "SenhaPacienteA123"},
    )
    assert pwd_cross.status_code == 401

    # OTP emitted for Patient A fails when verifying Patient B phone -> 401
    verify_cross = await async_client.post(
        "/api/v1/auth/patient/otp/verify",
        json={"telefone": "11987654339", "codigo": otp_a},
    )
    assert verify_cross.status_code == 401
    assert cast("dict[str, object]", verify_cross.json())["code"] == "OTP_INVALIDO"


@pytest.mark.asyncio
async def test_patient_identify_valkey_rate_limit_429(
    async_client: AsyncClient,
) -> None:
    """Validate real Valkey sliding window rate limit on /auth/patient/identify."""
    ident = "ratelimit.valkey@example.com"

    for _ in range(10):
        resp = await async_client.post(
            "/api/v1/auth/patient/identify",
            json={"identificador": ident},
        )
        assert resp.status_code == 200

    # Verify sliding window key recorded in live Valkey
    ident_hash = hashlib.sha256(ident.encode("utf-8")).hexdigest()[:16]
    valkey_key = f"auth:ratelimit:ratelimit:identify:id:{ident_hash}"
    valkey_client = Redis(connection_pool=get_valkey_pool())
    assert await valkey_client.zcard(valkey_key) == 10

    limited = await async_client.post(
        "/api/v1/auth/patient/identify",
        json={"identificador": ident},
    )
    assert limited.status_code == 429
    err = cast("dict[str, object]", limited.json())
    assert err["code"] == "IDENTIFY_RATE_LIMIT_EXCEEDED"
    assert int(limited.headers["retry-after"]) >= 1


@pytest.mark.asyncio
async def test_patient_register_debug_false_oculta_codigo_debug(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate codigo_debug is None in /register response when DEBUG=False."""
    fake_sms = cast("FakeSmsSenderAdapter", get_sms_sender())
    fake_sms.clear()

    monkeypatch.setattr(
        "src.modules.auth.composition.get_settings",
        lambda: DevelopmentSettings(DEBUG=False),
    )

    resp = await async_client.post(
        "/api/v1/auth/patient/register",
        json={
            "cpf": "11144477735",
            "nome_completo": "Paciente Producao",
            "data_nascimento": "1994-09-12",
            "telefone": "11987654332",
            "aceite_privacidade": True,
            "email": "paciente.nodebug@example.com",
            "senha": "SenhaSegura123",
        },
    )
    assert resp.status_code == 201
    data = cast("dict[str, object]", resp.json())
    assert data["otp_enviado"] is True
    assert data["codigo_debug"] is None
    assert len(fake_sms.sent_otps) == 1
