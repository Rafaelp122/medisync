"""Integration tests for patient passwordless OTP authentication endpoints."""

from typing import TYPE_CHECKING, cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.modules.identity.composition import get_sms_sender

if TYPE_CHECKING:
    from src.modules.identity.infrastructure.fake_sms_adapter import (
        FakeSmsSenderAdapter,
    )

from tests.factories.identity import make_organizacao, make_paciente

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_patient_otp_lifecycle_e2e(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate full passwordless OTP lifecycle: request, receive, verify, issue JWT."""
    # 1. Setup tenant and registered patient
    org = make_organizacao(cnpj="11223344000188")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    paciente = make_paciente(
        organizacao_id=org.id,
        cpf="11144477735",
        telefone="11987654321",
        nome_completo="Juliana Silva",
    )
    db_session.add(paciente)
    await db_session.commit()
    await db_session.refresh(paciente)

    fake_sms = cast("FakeSmsSenderAdapter", get_sms_sender())
    fake_sms.clear()

    headers = {"X-Tenant-ID": str(org.id)}

    # 2. Request OTP
    req_resp = await async_client.post(
        "/api/v1/auth/patient/otp/request",
        json={"telefone": "11987654321"},
        headers=headers,
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
        headers=headers,
    )
    assert verify_resp.status_code == 200
    verify_data = cast("dict[str, object]", verify_resp.json())
    assert "access_token" in verify_data
    assert verify_data["token_type"] == "bearer"
    assert verify_data["paciente_id"] == str(paciente.id)

    # 4. Validate JWT Token claims and role
    token = cast("str", verify_data["access_token"])
    user = decode_access_token(token)
    assert user.usuario_id == paciente.id
    assert user.organizacao_id == org.id
    assert user.papel == Role.PACIENTE.value
    assert user.has_permission("patient:queue_track")
    assert user.has_permission("patient:doc_view")


@pytest.mark.asyncio
async def test_patient_otp_paciente_nao_encontrado_retorna_404(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate 404 RFC 7807 is returned when phone is not registered in tenant."""
    org = make_organizacao(cnpj="11223344000189")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    headers = {"X-Tenant-ID": str(org.id)}

    resp = await async_client.post(
        "/api/v1/auth/patient/otp/request",
        json={"telefone": "11999998888"},
        headers=headers,
    )
    assert resp.status_code == 404
    data = cast("dict[str, object]", resp.json())
    assert data["code"] == "PACIENTE_NAO_ENCONTRADO"


@pytest.mark.asyncio
async def test_patient_otp_rate_limiting_retorna_429(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate 429 Too Many Requests after 3 OTP requests in sliding window."""
    org = make_organizacao(cnpj="11223344000190")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    paciente = make_paciente(
        organizacao_id=org.id,
        cpf="11144477735",
        telefone="11987654322",
    )
    db_session.add(paciente)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(org.id)}

    for _ in range(3):
        r = await async_client.post(
            "/api/v1/auth/patient/otp/request",
            json={"telefone": "11987654322"},
            headers=headers,
        )
        assert r.status_code == 200

    # 4th request must be rate-limited
    r_limited = await async_client.post(
        "/api/v1/auth/patient/otp/request",
        json={"telefone": "11987654322"},
        headers=headers,
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
    org = make_organizacao(cnpj="11223344000191")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    paciente = make_paciente(
        organizacao_id=org.id,
        cpf="11144477735",
        telefone="11987654323",
    )
    db_session.add(paciente)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(org.id)}

    await async_client.post(
        "/api/v1/auth/patient/otp/request",
        json={"telefone": "11987654323"},
        headers=headers,
    )

    verify_resp = await async_client.post(
        "/api/v1/auth/patient/otp/verify",
        json={"telefone": "11987654323", "codigo": "000000"},
        headers=headers,
    )
    assert verify_resp.status_code == 401
    err_data = cast("dict[str, object]", verify_resp.json())
    assert err_data["code"] == "OTP_INVALIDO"


@pytest.mark.asyncio
async def test_patient_otp_sem_tenant_retorna_400(
    async_client: AsyncClient,
) -> None:
    """Validate request without X-Tenant-ID is rejected with 400 Bad Request."""
    resp = await async_client.post(
        "/api/v1/auth/patient/otp/request",
        json={"telefone": "11987654321"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patient_otp_aliases_sucesso(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate alias routes /pacientes/auth/otp/solicitar and /verificar."""
    org = make_organizacao(cnpj="11223344000192")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    paciente = make_paciente(
        organizacao_id=org.id,
        cpf="11144477735",
        telefone="11987654324",
        nome_completo="Marcos Alias",
    )
    db_session.add(paciente)
    await db_session.commit()

    fake_sms = cast("FakeSmsSenderAdapter", get_sms_sender())
    fake_sms.clear()

    headers = {"X-Tenant-ID": str(org.id)}

    solicitar_resp = await async_client.post(
        "/api/v1/pacientes/auth/otp/solicitar",
        json={"telefone": "11987654324"},
        headers=headers,
    )
    assert solicitar_resp.status_code == 200

    otp_code = fake_sms.sent_otps[0]["codigo"]

    verificar_resp = await async_client.post(
        "/api/v1/pacientes/auth/otp/verificar",
        json={"telefone": "11987654324", "codigo": otp_code},
        headers=headers,
    )
    assert verificar_resp.status_code == 200
    data = cast("dict[str, object]", verificar_resp.json())
    assert data["token_type"] == "bearer"
    assert data["paciente_id"] == str(paciente.id)
