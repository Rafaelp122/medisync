"""Unit tests for PatientAuthService passwordless OTP workflow."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.errors import TenantInvalidoError
from src.core.uuid7 import uuid7
from src.modules.auth.application.dtos import (
    SolicitarOtpInputDTO,
    VerificarOtpInputDTO,
)
from src.modules.auth.application.services.patient_auth_service import (
    PatientAuthService,
)
from src.modules.auth.domain.exceptions import (
    OtpInvalidoOuExpiradoError,
    OtpRateLimitExcedidoError,
    PacienteNaoEncontradoError,
)
from src.modules.identity.application.ports.identity_reader_port import (
    IdentityReaderPort,
    PacienteAuthLookupDTO,
)
from src.modules.identity.application.services.patient_auth_service import (
    PatientAuthService as IdentityPatientAuthService,
)
from src.modules.identity.infrastructure.fake_sms_adapter import FakeSmsSenderAdapter


@pytest.fixture
def fake_sms() -> FakeSmsSenderAdapter:
    adapter = FakeSmsSenderAdapter()
    adapter.clear()
    return adapter


@pytest.fixture
def mock_identity_reader() -> AsyncMock:
    return AsyncMock(spec=IdentityReaderPort)


def _make_mock_paciente(
    paciente_id: UUID | None = None,
    org_id: int = 1,
    telefone: str = "11987654321",
) -> PacienteAuthLookupDTO:
    return PacienteAuthLookupDTO(
        id=paciente_id or uuid7(),
        organizacao_id=org_id,
        telefone=telefone,
        cpf="11144477735",
        nome_completo="Carlos Teste",
    )


def test_backward_compatibility_reexport() -> None:
    assert IdentityPatientAuthService is PatientAuthService


@pytest.mark.asyncio
async def test_solicitar_otp_sucesso(
    mock_identity_reader: AsyncMock, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    mock_identity_reader.buscar_paciente_por_telefone.return_value = paciente

    service = PatientAuthService(
        identity_reader=mock_identity_reader,
        sms_sender=fake_sms,
    )

    dados = SolicitarOtpInputDTO(telefone="11987654321")
    output = await service.solicitar_otp(organizacao_id=1, dados=dados)

    assert output.mensagem == "Código de verificação enviado com sucesso."
    assert output.expira_em_segundos == 300
    # In dev/test with DEBUG=True settings, codigo_debug should be populated
    settings = get_settings()
    if settings.DEBUG:
        assert output.codigo_debug is not None
        assert len(output.codigo_debug) == 6
        assert output.codigo_debug.isdigit()

    assert len(fake_sms.sent_otps) == 1
    assert fake_sms.sent_otps[0]["telefone"] == "11987654321"
    assert len(fake_sms.sent_otps[0]["codigo"]) == 6
    mock_identity_reader.buscar_paciente_por_telefone.assert_awaited_once_with(
        organizacao_id=1,
        telefone="11987654321",
        cpf=None,
    )


@pytest.mark.asyncio
async def test_solicitar_otp_paciente_nao_encontrado(
    mock_identity_reader: AsyncMock, fake_sms: FakeSmsSenderAdapter
) -> None:
    mock_identity_reader.buscar_paciente_por_telefone.return_value = None

    service = PatientAuthService(
        identity_reader=mock_identity_reader,
        sms_sender=fake_sms,
    )

    dados = SolicitarOtpInputDTO(telefone="11987654321")
    with pytest.raises(PacienteNaoEncontradoError):
        await service.solicitar_otp(organizacao_id=1, dados=dados)

    assert len(fake_sms.sent_otps) == 0


@pytest.mark.asyncio
async def test_solicitar_otp_rate_limit_excedido(
    mock_identity_reader: AsyncMock, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    mock_identity_reader.buscar_paciente_por_telefone.return_value = paciente

    service = PatientAuthService(
        identity_reader=mock_identity_reader,
        sms_sender=fake_sms,
    )

    dados = SolicitarOtpInputDTO(telefone="11987654321")

    # 3 requests must succeed
    for _ in range(3):
        res = await service.solicitar_otp(organizacao_id=1, dados=dados)
        assert res.expira_em_segundos == 300

    # 4th request must be rejected with 429
    with pytest.raises(OtpRateLimitExcedidoError) as exc_info:
        await service.solicitar_otp(organizacao_id=1, dados=dados)

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "OTP_RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_verificar_otp_sucesso_emite_jwt(
    mock_identity_reader: AsyncMock, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente_id = uuid7()
    paciente = _make_mock_paciente(paciente_id=paciente_id)
    mock_identity_reader.buscar_paciente_por_telefone.return_value = paciente

    service = PatientAuthService(
        identity_reader=mock_identity_reader,
        sms_sender=fake_sms,
    )

    # 1. Request OTP
    req_dados = SolicitarOtpInputDTO(telefone="11987654321")
    await service.solicitar_otp(organizacao_id=10, dados=req_dados)

    codigo_enviado = fake_sms.sent_otps[0]["codigo"]

    # 2. Verify OTP
    verify_dados = VerificarOtpInputDTO(telefone="11987654321", codigo=codigo_enviado)
    output = await service.verificar_otp(organizacao_id=10, dados=verify_dados)

    assert output.paciente_id == paciente_id
    assert output.token_type == "bearer"
    assert output.access_token is not None

    # 3. Decode issued JWT
    user = decode_access_token(output.access_token)
    assert user.usuario_id == paciente_id
    assert user.organizacao_id == 10
    assert user.papel == Role.PACIENTE.value
    assert user.has_permission("patient:queue_track")
    assert user.has_permission("patient:doc_view")

    # 4. Immediate replay must fail (one-time use)
    with pytest.raises(OtpInvalidoOuExpiradoError):
        await service.verificar_otp(organizacao_id=10, dados=verify_dados)


@pytest.mark.asyncio
async def test_verificar_otp_codigo_incorreto(
    mock_identity_reader: AsyncMock, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    mock_identity_reader.buscar_paciente_por_telefone.return_value = paciente

    service = PatientAuthService(
        identity_reader=mock_identity_reader,
        sms_sender=fake_sms,
    )

    req_dados = SolicitarOtpInputDTO(telefone="11987654321")
    await service.solicitar_otp(organizacao_id=1, dados=req_dados)

    verify_dados = VerificarOtpInputDTO(telefone="11987654321", codigo="000000")
    with pytest.raises(OtpInvalidoOuExpiradoError) as exc_info:
        await service.verificar_otp(organizacao_id=1, dados=verify_dados)

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "OTP_INVALIDO"


@pytest.mark.asyncio
async def test_verificar_otp_bloqueio_por_forca_bruta(
    mock_identity_reader: AsyncMock, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    mock_identity_reader.buscar_paciente_por_telefone.return_value = paciente

    service = PatientAuthService(
        identity_reader=mock_identity_reader,
        sms_sender=fake_sms,
    )

    req_dados = SolicitarOtpInputDTO(telefone="11987654321")
    await service.solicitar_otp(organizacao_id=1, dados=req_dados)
    codigo_correto = fake_sms.sent_otps[0]["codigo"]

    # 3 falhas consecutivas
    for _ in range(3):
        with pytest.raises(OtpInvalidoOuExpiradoError):
            await service.verificar_otp(
                organizacao_id=1,
                dados=VerificarOtpInputDTO(telefone="11987654321", codigo="999999"),
            )

    # 4ª tentativa, mesmo com o código correto, deve falhar porque o OTP foi invalidado
    with pytest.raises(OtpInvalidoOuExpiradoError):
        await service.verificar_otp(
            organizacao_id=1,
            dados=VerificarOtpInputDTO(telefone="11987654321", codigo=codigo_correto),
        )


@pytest.mark.asyncio
async def test_tenant_invalido_rejeitado(mock_identity_reader: AsyncMock) -> None:
    service = PatientAuthService(identity_reader=mock_identity_reader)

    with pytest.raises(TenantInvalidoError):
        await service.solicitar_otp(
            organizacao_id=0,
            dados=SolicitarOtpInputDTO(telefone="11987654321"),
        )

    with pytest.raises(TenantInvalidoError):
        await service.verificar_otp(
            organizacao_id=-1,
            dados=VerificarOtpInputDTO(telefone="11987654321", codigo="123456"),
        )


@pytest.mark.asyncio
async def test_sem_identity_reader_raises_value_error() -> None:
    service = PatientAuthService(identity_reader=None)

    with pytest.raises(ValueError, match="IdentityReaderPort não configurado"):
        await service.solicitar_otp(
            organizacao_id=1,
            dados=SolicitarOtpInputDTO(telefone="11987654321"),
        )
