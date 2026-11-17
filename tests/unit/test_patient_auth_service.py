"""Unit tests for PatientAuthService passwordless OTP workflow."""

from datetime import date
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
from src.modules.auth.application.ports.identity_reader_port import (
    PacienteAuthLookupData,
)
from src.modules.auth.application.services.patient_auth_service import (
    PatientAuthService,
)
from src.modules.auth.domain.exceptions import (
    OtpInvalidoOuExpiradoError,
    OtpRateLimitExcedidoError,
    OtpTentativasExcedidasError,
    PacienteNaoEncontradoError,
)
from src.modules.identity.infrastructure.fake_sms_adapter import FakeSmsSenderAdapter

from tests.doubles import FakeIdentityReader


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
    org_id: int = 1,
    telefone: str = "11987654321",
) -> PacienteAuthLookupData:
    return PacienteAuthLookupData(
        id=paciente_id or uuid7(),
        organizacao_id=org_id,
        telefone=telefone,
        cpf="11144477735",
        nome_completo="Carlos Teste",
    )


@pytest.mark.asyncio
async def test_solicitar_otp_sucesso(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente

    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
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
    assert len(fake_identity_reader.lookups) == 1
    assert fake_identity_reader.lookups[0] == {
        "organizacao_id": 1,
        "telefone": "11987654321",
        "cpf": None,
    }


@pytest.mark.asyncio
async def test_solicitar_otp_sucesso_com_prefixo_internacional_e164(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente

    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    dados = SolicitarOtpInputDTO(telefone="+5511987654321")
    output = await service.solicitar_otp(organizacao_id=1, dados=dados)

    assert output.mensagem == "Código de verificação enviado com sucesso."
    assert len(fake_sms.sent_otps) == 1
    assert fake_sms.sent_otps[0]["telefone"] == "11987654321"


@pytest.mark.asyncio
async def test_solicitar_otp_paciente_nao_encontrado(
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    fake_identity_reader.paciente = None

    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    dados = SolicitarOtpInputDTO(telefone="11987654321")
    output = await service.solicitar_otp(organizacao_id=1, dados=dados)

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

    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
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
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente_id = uuid7()
    paciente = _make_mock_paciente(paciente_id=paciente_id)
    fake_identity_reader.paciente = paciente

    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
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
    assert output.role == "PACIENTE"

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
    fake_identity_reader: FakeIdentityReader, fake_sms: FakeSmsSenderAdapter
) -> None:
    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente

    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    req_dados = SolicitarOtpInputDTO(telefone="11987654321")
    await service.solicitar_otp(organizacao_id=1, dados=req_dados)

    verify_dados = VerificarOtpInputDTO(telefone="11987654321", codigo="000000")
    with pytest.raises(OtpInvalidoOuExpiradoError) as exc_info:
        await service.verificar_otp(organizacao_id=1, dados=verify_dados)

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

    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        expose_debug_otp=True,
    )

    req_dados = SolicitarOtpInputDTO(telefone="11987654321")
    await service.solicitar_otp(organizacao_id=1, dados=req_dados)
    codigo_correto = fake_sms.sent_otps[0]["codigo"]

    # Tentativa 1: falha com 401 e 2 restantes
    with pytest.raises(OtpInvalidoOuExpiradoError) as exc_info1:
        await service.verificar_otp(
            organizacao_id=1,
            dados=VerificarOtpInputDTO(telefone="11987654321", codigo="999999"),
        )
    assert exc_info1.value.status_code == 401
    assert "Restam 2 tentativa(s)" in exc_info1.value.detail

    # Tentativa 2: falha com 401 e 1 restante
    with pytest.raises(OtpInvalidoOuExpiradoError) as exc_info2:
        await service.verificar_otp(
            organizacao_id=1,
            dados=VerificarOtpInputDTO(telefone="11987654321", codigo="999999"),
        )
    assert exc_info2.value.status_code == 401
    assert "Restam 1 tentativa(s)" in exc_info2.value.detail

    # Tentativa 3: falha com 429 OtpTentativasExcedidasError (bloqueio por força bruta)
    with pytest.raises(OtpTentativasExcedidasError) as exc_info3:
        await service.verificar_otp(
            organizacao_id=1,
            dados=VerificarOtpInputDTO(telefone="11987654321", codigo="999999"),
        )
    assert exc_info3.value.status_code == 429
    assert exc_info3.value.code == "OTP_TENTATIVAS_EXCEDIDAS"
    assert exc_info3.value.headers == {"Retry-After": "900"}
    assert "1198****4321" in exc_info3.value.detail

    # Tentativa 4: código correto ou incorreto falha com 401
    # (OTP foi invalidado e removido)
    with pytest.raises(OtpInvalidoOuExpiradoError) as exc_info4:
        await service.verificar_otp(
            organizacao_id=1,
            dados=VerificarOtpInputDTO(telefone="11987654321", codigo=codigo_correto),
        )
    assert exc_info4.value.status_code == 401


@pytest.mark.asyncio
async def test_tenant_invalido_rejeitado(
    fake_identity_reader: FakeIdentityReader,
) -> None:
    service = PatientAuthService(identity_reader=fake_identity_reader)

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
    service = PatientAuthService(identity_reader=fake_identity_reader)

    # 1. Test error with CPF and CNS masks PII in exception detail
    with pytest.raises(PacienteNaoEncontradoError) as exc_info:
        await service.autenticar_cadsus_govbr(
            organizacao_id=1,
            cpf="11144477735",
            cns="898001234567890",
        )
    err_msg = str(exc_info.value.detail)
    assert "111.***.***-35" in err_msg
    assert "898********7890" in err_msg
    assert "11144477735" not in err_msg
    assert "898001234567890" not in err_msg

    # 2. Test error with only CPF masks CPF and marks CNS as N/A
    with pytest.raises(PacienteNaoEncontradoError) as exc_info2:
        await service.autenticar_cadsus_govbr(
            organizacao_id=1,
            cpf="11144477735",
        )
    err_msg2 = str(exc_info2.value.detail)
    assert "111.***.***-35" in err_msg2
    assert "CNS: N/A" in err_msg2


@pytest.mark.asyncio
async def test_autenticar_cadsus_desambiguacao_nome_mae(
    fake_identity_reader: FakeIdentityReader,
) -> None:
    paciente_carlos = PacienteAuthLookupData(
        id=uuid7(),
        organizacao_id=1,
        telefone="11987654321",
        cpf="11144477735",
        nome_completo="Carlos Silva",
        nome_mae="Maria Aparecida da Silva",
    )
    fake_identity_reader.paciente = paciente_carlos
    service = PatientAuthService(identity_reader=fake_identity_reader)

    res = await service.autenticar_cadsus_govbr(
        organizacao_id=1,
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
        organizacao_id=1,
        telefone="11987654321",
        cpf="11144477735",
        nome_completo="Carlos Silva",
        nome_mae="Joana da Silva",
    )
    p2 = PacienteAuthLookupData(
        id=uuid7(),
        organizacao_id=1,
        telefone="11987654322",
        cpf="11144477735",
        nome_completo="Carlos Silva",
        nome_mae="Maria Aparecida da Silva",
    )
    fake_identity_reader.pacientes = [p1, p2]
    service = PatientAuthService(identity_reader=fake_identity_reader)

    res = await service.autenticar_cadsus_govbr(
        organizacao_id=1,
        cpf="11144477735",
        nome_mae="maria aparecida da silva",
    )
    assert res.paciente_id == p2.id


@pytest.mark.asyncio
async def test_verificar_otp_sucesso_retorna_atendimento_ativo_quando_existente(
    fake_identity_reader: FakeIdentityReader,
    fake_sms: FakeSmsSenderAdapter,
) -> None:
    from src.modules.auth.application.ports.active_attendance_lookup_port import (
        ActiveAttendanceLookupPort,
    )

    paciente = _make_mock_paciente()
    fake_identity_reader.paciente = paciente
    atendimento_ativo_id = uuid7()

    class _FakeLookup(ActiveAttendanceLookupPort):
        async def buscar_atendimento_ativo_paciente(
            self, organizacao_id: int, paciente_id: UUID
        ) -> UUID | None:
            if organizacao_id == 1 and paciente_id == paciente.id:
                return atendimento_ativo_id
            return None

    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        active_attendance_lookup=_FakeLookup(),
        expose_debug_otp=True,
    )
    req_out = await service.solicitar_otp(
        organizacao_id=1,
        dados=SolicitarOtpInputDTO(telefone="11987654321"),
    )
    assert req_out.codigo_debug is not None
    ver_out = await service.verificar_otp(
        organizacao_id=1,
        dados=VerificarOtpInputDTO(
            telefone="11987654321",
            codigo=req_out.codigo_debug,
        ),
    )
    assert ver_out.atendimento_id == atendimento_ativo_id


@pytest.mark.asyncio
async def test_autenticar_cadsus_sem_cpf_e_sem_cns_interpola_valores_ofensivos(
    fake_identity_reader: FakeIdentityReader,
) -> None:
    service = PatientAuthService(identity_reader=fake_identity_reader)
    with pytest.raises(PacienteNaoEncontradoError, match="recebido cpf=None"):
        await service.autenticar_cadsus_govbr(
            organizacao_id=1,
            cpf=None,
            cns="   ",
        )


@pytest.mark.asyncio
async def test_patient_auth_service_default_oculta_codigo_debug(
    fake_identity_reader: FakeIdentityReader,
    fake_sms: FakeSmsSenderAdapter,
) -> None:
    """Por padrão seguro, PatientAuthService não expõe codigo_debug."""
    fake_identity_reader.paciente = _make_mock_paciente()
    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
    )

    output = await service.solicitar_otp(
        organizacao_id=1,
        dados=SolicitarOtpInputDTO(telefone="11987654321"),
    )
    assert output.codigo_debug is None
    assert len(fake_sms.sent_otps) == 1


@pytest.mark.asyncio
async def test_solicitar_otp_usa_auth_rate_limiter_port_quando_injetado(
    fake_identity_reader: FakeIdentityReader,
    fake_sms: FakeSmsSenderAdapter,
) -> None:
    """Quando rate_limiter é injetado, solicitar_otp delega para AuthRateLimiterPort."""
    from src.modules.auth.infrastructure.valkey_rate_limiter import FakeAuthRateLimiter

    fake_identity_reader.paciente = _make_mock_paciente()
    limiter = FakeAuthRateLimiter()
    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        sms_sender=fake_sms,
        rate_limiter=limiter,
    )

    dados = SolicitarOtpInputDTO(telefone="11987654321")
    for _ in range(3):
        await service.solicitar_otp(organizacao_id=1, dados=dados)

    with pytest.raises(OtpRateLimitExcedidoError) as exc_info:
        await service.solicitar_otp(organizacao_id=1, dados=dados)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers


@pytest.mark.asyncio
async def test_valkey_sliding_window_hashes_pii_and_uses_window_seconds(
    fake_identity_reader: FakeIdentityReader,
    fake_sms: FakeSmsSenderAdapter,
) -> None:
    """Chaves Valkey devem hashear PII e Retry-After deve respeitar window_seconds."""
    import time
    from typing import Any

    from redis.asyncio import Redis
    from src.modules.auth.application.dtos import IdentificarPacienteCommand

    class _ZSetValkeyPipeline:
        def __init__(self, store: "_ZSetFakeValkey") -> None:
            self._store = store
            self._ops: list[tuple[str, Any]] = []

        async def __aenter__(self) -> "_ZSetValkeyPipeline":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def zremrangebyscore(
            self, key: str, min_score: float, max_score: float
        ) -> None:
            self._ops.append(("zremrangebyscore", (key, min_score, max_score)))

        async def zcard(self, key: str) -> None:
            self._ops.append(("zcard", key))

        async def zadd(self, key: str, mapping: dict[str, float]) -> None:
            self._ops.append(("zadd", (key, mapping)))

        async def expire(self, key: str, seconds: int) -> None:
            self._ops.append(("expire", (key, seconds)))

        async def execute(self) -> list[Any]:
            results: list[Any] = []
            for op, arg in self._ops:
                if op == "zremrangebyscore":
                    key, min_s, max_s = arg
                    zset = self._store.zsets.setdefault(key, {})
                    to_del = [m for m, s in zset.items() if min_s <= s <= max_s]
                    for m in to_del:
                        del zset[m]
                    results.append(len(to_del))
                elif op == "zcard":
                    results.append(len(self._store.zsets.get(arg, {})))
                elif op == "zadd":
                    key, mapping = arg
                    zset = self._store.zsets.setdefault(key, {})
                    zset.update(mapping)
                    results.append(len(mapping))
                elif op == "expire":
                    results.append(True)
            self._ops.clear()
            return results

    class _ZSetFakeValkey:
        def __init__(self) -> None:
            self.zsets: dict[str, dict[str, float]] = {}
            self.kv: dict[str, str] = {}

        def pipeline(self, transaction: bool = True) -> _ZSetValkeyPipeline:
            return _ZSetValkeyPipeline(self)

        async def set(self, key: str, value: str, ex: int | None = None) -> bool:
            self.kv[key] = value
            return True

        async def zrange(
            self, key: str, start: int, end: int, withscores: bool = False
        ) -> list[tuple[str, float]]:
            items = sorted(self.zsets.get(key, {}).items(), key=lambda x: x[1])
            sliced = items[start : end + 1 if end >= 0 else None]
            return sliced if withscores else [(m, 0.0) for m, _ in sliced]  # type: ignore[return-value]

    valkey = _ZSetFakeValkey()
    fake_identity_reader.paciente = _make_mock_paciente(telefone="11987654321")
    service = PatientAuthService(
        identity_reader=fake_identity_reader,
        valkey_client=valkey,  # type: ignore[arg-type]
        sms_sender=fake_sms,
    )

    await service.solicitar_otp(
        organizacao_id=1,
        dados=SolicitarOtpInputDTO(telefone="11987654321"),
    )
    await service.identificar_paciente(
        IdentificarPacienteCommand(
            organizacao_id=1,
            identificador="paciente.sigiloso@example.com",
            client_ip="10.1.2.3",
        )
    )

    assert len(valkey.zsets) == 3
    for key in valkey.zsets:
        assert "11987654321" not in key
        assert "paciente.sigiloso@example.com" not in key

    # Validate _calculate_valkey_retry_after uses the provided window_seconds (e.g. 120)
    custom_key = "ratelimit:custom:test"
    now = time.time()
    valkey.zsets[custom_key] = {"entry-1": now - 10}
    retry_after = await service._calculate_valkey_retry_after(  # pyright: ignore[reportPrivateUsage]
        custom_key, now, 120
    )
    assert 105 <= retry_after <= 110
    assert isinstance(valkey, object) and Redis is not None
