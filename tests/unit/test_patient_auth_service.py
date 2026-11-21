"""Unit tests for PatientAuthService passwordless OTP & CADSUS workflows."""

import asyncio
from datetime import date
from uuid import UUID

import pytest
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.errors import ServiceUnavailableError, ValidationError
from src.core.uuid7 import uuid7
from src.modules.auth.application.dtos import (
    IdentificarPacienteCommand,
    RateLimitResultDTO,
)
from src.modules.auth.application.ports.active_attendance_lookup_port import (
    ActiveAttendanceLookupPort,
)
from src.modules.auth.application.ports.auth_rate_limiter_port import (
    AuthRateLimiterPort,
)
from src.modules.auth.application.ports.identity_reader_port import (
    PacienteAuthLookupData,
)
from src.modules.auth.application.services.patient_auth_service import (
    CADSUS_MAX_REQUESTS_PER_IP,
    PatientAuthService,
)
from src.modules.auth.domain.exceptions import (
    IdentificacaoRateLimitExcedidoError,
    OtpInvalidoOuExpiradoError,
    OtpRateLimitExcedidoError,
    OtpTentativasExcedidasError,
    PacienteNaoEncontradoError,
)
from src.modules.auth.infrastructure.fake_sms_adapter import FakeSmsSenderAdapter
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.auth.infrastructure.valkey_challenge_store import (
    ValkeyChallengeStore,
)
from src.modules.auth.infrastructure.valkey_rate_limiter import FakeAuthRateLimiter
from src.modules.auth.presentation.schemas import (
    SolicitarOtpRequest,
    VerificarOtpRequest,
)

from tests.doubles import FakeIdentityReader, MemoryChallengeStore

_TEST_JWT_SECRET = "test-patient-auth-secret-key-min-32-chars"


class _SpyAuthRateLimiter(AuthRateLimiterPort):
    """Named fake delegating to FakeAuthRateLimiter while recording emitted keys."""

    def __init__(self) -> None:
        self._inner = FakeAuthRateLimiter()
        self.keys_checked: list[str] = []

    async def verificar_e_incrementar(
        self,
        chave: str,
        limite: int = 5,
        janela_segundos: int = 900,
    ) -> RateLimitResultDTO:
        self.keys_checked.append(chave)
        return await self._inner.verificar_e_incrementar(
            chave=chave,
            limite=limite,
            janela_segundos=janela_segundos,
        )

    async def resetar(self, chave: str) -> None:
        await self._inner.resetar(chave)


class _FailingChallengeRedis:
    """Named fake simulating Valkey outage to verify fail-closed 503."""

    async def set(self, *args: object, **kwargs: object) -> bool:
        raise RuntimeError("Valkey connection refused")

    async def getdel(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError("Valkey connection refused")

    async def eval(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError("Valkey connection refused")


@pytest.fixture
def fake_sms() -> FakeSmsSenderAdapter:
    adapter = FakeSmsSenderAdapter()
    adapter.clear()
    return adapter


@pytest.fixture
def fake_identity_reader() -> FakeIdentityReader:
    return FakeIdentityReader()


def _make_mock_paciente(
    paciente_id: UUID | None = None,
    telefone: str = "11987654321",
    data_nascimento: date = date(1990, 5, 15),
) -> PacienteAuthLookupData:
    return PacienteAuthLookupData(
        id=paciente_id or uuid7(),
        telefone=telefone,
        cpf="11144477735",
        nome_completo="Carlos Teste",
        nome_mae="Maria Teste",
        data_nascimento=data_nascimento,
    )


def _make_service(
    *,
    identity_reader: FakeIdentityReader | None = None,
    sms_sender: FakeSmsSenderAdapter | None = None,
    challenge_store: MemoryChallengeStore | None = None,
    rate_limiter: AuthRateLimiterPort | None = None,
    active_attendance_lookup: ActiveAttendanceLookupPort | None = None,
    expose_debug_otp: bool = False,
) -> PatientAuthService:
    settings = get_settings()
    return PatientAuthService(
        token_service=JWTTokenService(
            secret_key=settings.JWT_SECRET_KEY or _TEST_JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
            access_token_expire_minutes=15,
        ),
        challenge_store=challenge_store or MemoryChallengeStore(),
        rate_limiter=rate_limiter or FakeAuthRateLimiter(),
        identity_reader=identity_reader,
        sms_sender=sms_sender,
        expose_debug_otp=expose_debug_otp,
        active_attendance_lookup=active_attendance_lookup,
    )


@pytest.mark.asyncio
async def test_solicitar_otp_sucesso(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente

    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    dados = SolicitarOtpRequest(telefone="11987654321")
    output = await service.solicitar_otp(dados=dados)

    assert output.mensagem == "Código de verificação enviado com sucesso."
    assert output.expira_em_segundos == 300
    assert output.codigo_debug is not None
    assert len(output.codigo_debug) == 6
    assert output.codigo_debug.isdigit()

    assert len(fake_sms.sent_otps) == 1
    assert fake_sms.sent_otps[0]["telefone"] == "11987654321"
    assert len(fake_sms.sent_otps[0]["codigo"]) == 6
    assert len(fake_identity_reader.lookups) == 1
    assert fake_identity_reader.lookups[0] == {
        "telefone": "11987654321",
        "cpf": None,
    }


@pytest.mark.asyncio
async def test_solicitar_otp_sucesso_com_prefixo_internacional_e164(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente

    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    dados = SolicitarOtpRequest(telefone="+5511987654321")
    output = await service.solicitar_otp(dados=dados)

    assert output.mensagem == "Código de verificação enviado com sucesso."
    assert len(fake_sms.sent_otps) == 1
    assert fake_sms.sent_otps[0]["telefone"] == "11987654321"


@pytest.mark.asyncio
async def test_solicitar_otp_paciente_nao_encontrado(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    fake_identity_reader.paciente = None

    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    dados = SolicitarOtpRequest(telefone="11987654321")
    output = await service.solicitar_otp(dados=dados)

    assert output.mensagem == "Código de verificação enviado com sucesso."
    assert output.expira_em_segundos == 300
    assert output.codigo_debug is None
    assert len(fake_sms.sent_otps) == 0


@pytest.mark.asyncio
async def test_solicitar_otp_rate_limit_excedido(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente

    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    dados = SolicitarOtpRequest(telefone="11987654321")

    for _ in range(3):
        res = await service.solicitar_otp(dados=dados)
        assert res.expira_em_segundos == 300

    with pytest.raises(OtpRateLimitExcedidoError) as exc_info:
        await service.solicitar_otp(dados=dados)

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "OTP_RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_verificar_otp_sucesso_emite_jwt(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente_id = uuid7()
    paciente = _make_mock_paciente(paciente_id=paciente_id)
    fake_identity_reader.paciente = paciente

    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    req_dados = SolicitarOtpRequest(telefone="11987654321")
    await service.solicitar_otp(dados=req_dados)

    codigo_enviado = fake_sms.sent_otps[0]["codigo"]

    verify_dados = VerificarOtpRequest(telefone="11987654321", codigo=codigo_enviado)
    output = await service.verificar_otp(dados=verify_dados)

    assert output.paciente_id == paciente_id
    assert output.token_type == "bearer"
    assert output.expires_in == 900
    assert output.access_token is not None
    assert output.role == "PACIENTE"

    user = decode_access_token(output.access_token)
    assert user.usuario_id == paciente_id
    assert not hasattr(user, "organizacao_id")
    assert user.papel == Role.PACIENTE.value
    assert user.has_permission("patient:queue_track")
    assert user.has_permission("patient:doc_view")

    with pytest.raises(OtpInvalidoOuExpiradoError):
        await service.verificar_otp(dados=verify_dados)


@pytest.mark.asyncio
async def test_verificar_otp_concorrencia_atomica_apenas_um_sucesso(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    """Corrida em /otp/verify via verify_and_increment_otp permite só 1 uso."""
    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente
    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    await service.solicitar_otp(dados=SolicitarOtpRequest(telefone="11987654321"))
    codigo = fake_sms.sent_otps[0]["codigo"]
    verify_req = VerificarOtpRequest(telefone="11987654321", codigo=codigo)

    results = await asyncio.gather(
        *(service.verificar_otp(dados=verify_req) for _ in range(5)),
        return_exceptions=True,
    )
    sucessos = [r for r in results if not isinstance(r, BaseException)]
    falhas = [r for r in results if isinstance(r, OtpInvalidoOuExpiradoError)]
    assert len(sucessos) == 1
    assert len(falhas) == 4


@pytest.mark.asyncio
async def test_verificar_otp_codigo_incorreto(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente

    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    req_dados = SolicitarOtpRequest(telefone="11987654321")
    await service.solicitar_otp(dados=req_dados)

    verify_dados = VerificarOtpRequest(telefone="11987654321", codigo="000000")
    with pytest.raises(OtpInvalidoOuExpiradoError) as exc_info:
        await service.verificar_otp(dados=verify_dados)

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "OTP_INVALIDO"
    assert "1198****4321" in exc_info.value.detail
    assert "Restam 2 tentativa(s)" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verificar_otp_bloqueio_por_forca_bruta(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente

    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    req_dados = SolicitarOtpRequest(telefone="11987654321")
    await service.solicitar_otp(dados=req_dados)
    codigo_correto = fake_sms.sent_otps[0]["codigo"]

    with pytest.raises(OtpInvalidoOuExpiradoError) as exc_info1:
        await service.verificar_otp(
            dados=VerificarOtpRequest(telefone="11987654321", codigo="999999"),
        )
    assert exc_info1.value.status_code == 401
    assert "Restam 2 tentativa(s)" in exc_info1.value.detail

    with pytest.raises(OtpInvalidoOuExpiradoError) as exc_info2:
        await service.verificar_otp(
            dados=VerificarOtpRequest(telefone="11987654321", codigo="999999"),
        )
    assert exc_info2.value.status_code == 401
    assert "Restam 1 tentativa(s)" in exc_info2.value.detail

    with pytest.raises(OtpTentativasExcedidasError) as exc_info3:
        await service.verificar_otp(
            dados=VerificarOtpRequest(telefone="11987654321", codigo="999999"),
        )
    assert exc_info3.value.status_code == 429
    assert exc_info3.value.code == "OTP_TENTATIVAS_EXCEDIDAS"
    assert exc_info3.value.headers == {"Retry-After": "900"}
    assert "1198****4321" in exc_info3.value.detail

    with pytest.raises(OtpInvalidoOuExpiradoError) as exc_info4:
        await service.verificar_otp(
            dados=VerificarOtpRequest(telefone="11987654321", codigo=codigo_correto),
        )
    assert exc_info4.value.status_code == 401


@pytest.mark.asyncio
async def test_sem_identity_reader_raises_value_error() -> None:
    service = _make_service(identity_reader=None)

    with pytest.raises(ValueError, match="IdentityReaderPort não configurado"):
        await service.solicitar_otp(
            dados=SolicitarOtpRequest(telefone="11987654321"),
        )


def test_mascarar_cns() -> None:
    from src.core.privacy import mascarar_cns

    assert mascarar_cns("898001234567890") == "898********7890"
    assert mascarar_cns("898 0012 3456 7890") == "898********7890"
    assert mascarar_cns("123") == "***"
    assert mascarar_cns("") == "***"


@pytest.mark.asyncio
async def test_autenticar_cadsus_mascaramento_cpf_cns_no_erro(
    fake_identity_reader: FakeIdentityReader,
) -> None:
    fake_identity_reader.paciente = None
    service = _make_service(identity_reader=fake_identity_reader)

    with pytest.raises(PacienteNaoEncontradoError) as exc_info:
        await service.autenticar_cadsus_govbr(
            cpf="11144477735",
            cns="800000000000001",
            data_nascimento=date(1990, 5, 15),
        )
    err_msg = str(exc_info.value.detail)
    assert "111.***.***-35" in err_msg
    assert "800********0001" in err_msg
    assert "11144477735" not in err_msg
    assert "800000000000001" not in err_msg

    with pytest.raises(PacienteNaoEncontradoError) as exc_info2:
        await service.autenticar_cadsus_govbr(
            cpf="11144477735",
            data_nascimento=date(1990, 5, 15),
            nome_mae="Maria da Silva",
        )
    err_msg2 = str(exc_info2.value.detail)
    assert "111.***.***-35" in err_msg2
    assert "CNS: N/A" in err_msg2


@pytest.mark.asyncio
async def test_autenticar_cadsus_rejeita_cns_invalido_e_falta_segundo_fator(
    fake_identity_reader: FakeIdentityReader,
) -> None:
    """CADSUS rejects invalid CNS, missing DOB, or CPF without 2nd factor."""
    service = _make_service(identity_reader=fake_identity_reader)

    with pytest.raises(ValidationError, match="Data de nascimento é obrigatória"):
        await service.autenticar_cadsus_govbr(
            cpf="11144477735",
            nome_mae="Maria da Silva",
        )

    with pytest.raises(ValidationError, match="segundo fator civil"):
        await service.autenticar_cadsus_govbr(
            cpf="11144477735",
            data_nascimento=date(1990, 5, 15),
        )

    with pytest.raises(ValidationError, match=r"898\*\*\*\*\*\*\*\*7890"):
        await service.autenticar_cadsus_govbr(
            cns="898001234567890",
            data_nascimento=date(1990, 5, 15),
        )


@pytest.mark.asyncio
async def test_autenticar_cadsus_desambiguacao_nome_mae(
    fake_identity_reader: FakeIdentityReader,
) -> None:
    paciente_carlos = PacienteAuthLookupData(
        id=uuid7(),
        telefone="11987654321",
        cpf="11144477735",
        nome_completo="Carlos Silva",
        nome_mae="Maria Aparecida da Silva",
        data_nascimento=date(1990, 5, 15),
    )
    fake_identity_reader.paciente = paciente_carlos
    service = _make_service(identity_reader=fake_identity_reader)

    res = await service.autenticar_cadsus_govbr(
        cpf="11144477735",
        data_nascimento=date(1990, 5, 15),
        nome_mae="Maria Aparecida da Silva",
    )
    assert res.paciente_id == paciente_carlos.id
    assert len(fake_identity_reader.lookups) == 1
    assert fake_identity_reader.lookups[0]["nome_mae"] == "Maria Aparecida da Silva"


@pytest.mark.asyncio
async def test_autenticar_cadsus_filtro_por_nome_mae_com_multiplos_pacientes(
    fake_identity_reader: FakeIdentityReader,
) -> None:
    p1 = PacienteAuthLookupData(
        id=uuid7(),
        telefone="11987654321",
        cpf="11144477735",
        nome_completo="Carlos Silva",
        nome_mae="Joana da Silva",
        data_nascimento=date(1990, 5, 15),
    )
    p2 = PacienteAuthLookupData(
        id=uuid7(),
        telefone="11987654322",
        cpf="11144477735",
        nome_completo="Carlos Silva",
        nome_mae="Maria Aparecida da Silva",
        data_nascimento=date(1990, 5, 15),
    )
    fake_identity_reader.pacientes = [p1, p2]
    service = _make_service(identity_reader=fake_identity_reader)

    res = await service.autenticar_cadsus_govbr(
        cpf="11144477735",
        data_nascimento=date(1990, 5, 15),
        nome_mae="maria aparecida da silva",
    )
    assert res.paciente_id == p2.id


@pytest.mark.asyncio
async def test_autenticar_cadsus_cpf_com_cns_sanitizado_e_atendimento_ativo(
    fake_identity_reader: FakeIdentityReader,
) -> None:
    """CADSUS accepts CPF + formatted CNS + DOB and populates active atendimento_id."""
    paciente_id = uuid7()
    atendimento_ativo_id = uuid7()
    fake_identity_reader.paciente = PacienteAuthLookupData(
        id=paciente_id,
        telefone="11987654321",
        cpf="11144477735",
        cns="800000000000001",
        nome_completo="Carlos SUS",
        data_nascimento=date(1988, 3, 10),
    )

    class _FakeLookup(ActiveAttendanceLookupPort):
        async def buscar_atendimento_ativo_paciente(
            self, paciente_id: UUID
        ) -> UUID | None:
            return atendimento_ativo_id

    service = _make_service(
        identity_reader=fake_identity_reader,
        active_attendance_lookup=_FakeLookup(),
    )

    res = await service.autenticar_cadsus_govbr(
        cpf="111.444.777-35",
        cns="800.0000.0000.0001",
        data_nascimento=date(1988, 3, 10),
    )
    assert res.paciente_id == paciente_id
    assert res.atendimento_id == atendimento_ativo_id
    assert fake_identity_reader.lookups[0]["cns"] == "800000000000001"


@pytest.mark.asyncio
async def test_autenticar_cadsus_rate_limit_por_ip(
    fake_identity_reader: FakeIdentityReader,
) -> None:
    """CADSUS endpoint enforces per-IP rate limiting (429)."""
    fake_identity_reader.paciente = None
    service = _make_service(identity_reader=fake_identity_reader)

    for _ in range(CADSUS_MAX_REQUESTS_PER_IP):
        with pytest.raises(PacienteNaoEncontradoError):
            await service.autenticar_cadsus_govbr(
                cpf="11144477735",
                data_nascimento=date(1990, 5, 15),
                nome_mae="Maria",
                client_ip="203.0.113.10",
            )

    with pytest.raises(IdentificacaoRateLimitExcedidoError) as exc_info:
        await service.autenticar_cadsus_govbr(
            cpf="11144477735",
            data_nascimento=date(1990, 5, 15),
            nome_mae="Maria",
            client_ip="203.0.113.10",
        )
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_verificar_otp_sucesso_retorna_atendimento_ativo_quando_existente(
    fake_identity_reader: FakeIdentityReader,
    fake_sms: FakeSmsSenderAdapter,
) -> None:
    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente
    atendimento_ativo_id = uuid7()

    class _FakeLookup(ActiveAttendanceLookupPort):
        async def buscar_atendimento_ativo_paciente(
            self, paciente_id: UUID
        ) -> UUID | None:
            return atendimento_ativo_id if paciente_id == paciente.id else None

    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        active_attendance_lookup=_FakeLookup(),
        expose_debug_otp=True,
    )
    req_out = await service.solicitar_otp(
        dados=SolicitarOtpRequest(telefone="11987654321"),
    )
    assert req_out.codigo_debug is not None
    ver_out = await service.verificar_otp(
        dados=VerificarOtpRequest(
            telefone="11987654321",
            codigo=req_out.codigo_debug,
        ),
    )
    assert ver_out.atendimento_id == atendimento_ativo_id


@pytest.mark.asyncio
async def test_autenticar_cadsus_sem_cpf_e_sem_cns_interpola_valores_ofensivos(
    fake_identity_reader: FakeIdentityReader,
) -> None:
    service = _make_service(identity_reader=fake_identity_reader)
    with pytest.raises(ValidationError, match="recebido cpf=None"):
        await service.autenticar_cadsus_govbr(
            cpf=None,
            cns="   ",
            data_nascimento=date(1990, 5, 15),
        )


@pytest.mark.asyncio
async def test_patient_auth_service_default_oculta_codigo_debug(
    fake_identity_reader: FakeIdentityReader,
    fake_sms: FakeSmsSenderAdapter,
) -> None:
    """Por padrão seguro, PatientAuthService não expõe codigo_debug."""
    fake_identity_reader.paciente = _make_mock_paciente()
    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
    )

    output = await service.solicitar_otp(
        dados=SolicitarOtpRequest(telefone="11987654321"),
    )
    assert output.codigo_debug is None
    assert len(fake_sms.sent_otps) == 1


@pytest.mark.asyncio
async def test_solicitar_otp_usa_auth_rate_limiter_port_sem_duplo_prefixo(
    fake_identity_reader: FakeIdentityReader,
    fake_sms: FakeSmsSenderAdapter,
) -> None:
    """Rate limiting uses AuthRateLimiterPort with hashed PII and clean key."""
    fake_identity_reader.paciente = _make_mock_paciente()
    limiter = _SpyAuthRateLimiter()
    service = _make_service(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        rate_limiter=limiter,
    )

    dados = SolicitarOtpRequest(telefone="11987654321")
    for _ in range(3):
        await service.solicitar_otp(dados=dados)

    await service.identificar_paciente(
        IdentificarPacienteCommand(
            identificador="paciente.sigiloso@example.com",
            client_ip="10.1.2.3",
        )
    )

    assert len(limiter.keys_checked) == 5
    for key in limiter.keys_checked:
        assert not key.startswith("ratelimit:")
        assert "11987654321" not in key
        assert "paciente.sigiloso@example.com" not in key

    with pytest.raises(OtpRateLimitExcedidoError) as exc_info:
        await service.solicitar_otp(dados=dados)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers


@pytest.mark.asyncio
async def test_valkey_challenge_store_fail_closed_sem_fallback_em_memoria() -> None:
    """ValkeyChallengeStore aborts fail-closed with 503 when Valkey errors occur."""
    store = ValkeyChallengeStore(client=_FailingChallengeRedis())  # type: ignore[arg-type]

    with pytest.raises(ServiceUnavailableError):
        await store.store_one_time("otp:11987654321", "payload", 300)

    with pytest.raises(ServiceUnavailableError):
        await store.consume_one_time("webauthn:reg:test")

    with pytest.raises(ServiceUnavailableError):
        await store.verify_and_increment_otp("otp:11987654321", "hash", 3)
