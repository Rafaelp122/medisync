"""Unit tests for Patient Hybrid IAM (register, identify, password, methods)."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import CommonSettings, get_settings
from src.core.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from src.modules.auth.application.dtos import (
    IdentificarPacienteCommand,
    LoginPacienteSenhaCommand,
    RegistrarPacienteCommand,
)
from src.modules.auth.application.services.patient_auth_service import (
    PatientAuthService,
)
from src.modules.auth.domain.exceptions import (
    ContaBloqueadaError,
    ContaDesativadaError,
    CredenciaisInvalidasError,
    IdentificacaoRateLimitExcedidoError,
)
from src.modules.auth.infrastructure.fake_sms_adapter import FakeSmsSenderAdapter
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.auth.infrastructure.valkey_rate_limiter import FakeAuthRateLimiter

from tests.doubles import (
    FakeAsyncSession,
    FakeIdentityReader,
    FakeIdentityWriter,
    FakePasswordHasher,
    FakePatientCredentialRepository,
    MemoryChallengeStore,
)


def _build_service(
    *,
    govbr_oidc_enabled: bool = False,
    expose_debug_otp: bool = True,
) -> tuple[
    PatientAuthService,
    FakeIdentityReader,
    FakeIdentityWriter,
    FakePatientCredentialRepository,
    FakePasswordHasher,
    FakeSmsSenderAdapter,
    FakeAsyncSession,
]:
    reader = FakeIdentityReader(pacientes=[])
    writer = FakeIdentityWriter(reader)
    cred_repo = FakePatientCredentialRepository()
    hasher = FakePasswordHasher()
    sms = FakeSmsSenderAdapter()
    sms.clear()
    session = FakeAsyncSession()
    settings = get_settings()
    service = PatientAuthService(
        token_service=JWTTokenService(
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            access_token_expire_minutes=15,
        ),
        challenge_store=MemoryChallengeStore(),
        rate_limiter=FakeAuthRateLimiter(),
        identity_reader=reader,
        sms_sender=sms,
        identity_writer=writer,
        credential_repo=cred_repo,
        password_hasher=hasher,
        govbr_oidc_enabled=govbr_oidc_enabled,
        expose_debug_otp=expose_debug_otp,
        session=session,  # type: ignore[arg-type]
    )
    return service, reader, writer, cred_repo, hasher, sms, session


@pytest.mark.asyncio
async def test_registrar_paciente_passwordless_envia_otp() -> None:
    service, reader, _, cred_repo, _, sms, session = _build_service()

    dados = RegistrarPacienteCommand(
        cpf="111.444.777-35",
        nome_completo="Maria da Silva",
        data_nascimento=date(1990, 5, 15),
        telefone="11987654321",
        email="maria.silva@example.com",
        aceite_privacidade=True,
    )
    out = await service.registrar_paciente(dados)

    assert out.paciente_id is not None
    assert out.telefone_mascarado == "1198****4321"
    assert out.otp_enviado is True
    assert out.expira_em_segundos == 300
    assert out.codigo_debug == sms.sent_otps[0]["codigo"]
    assert session.commits == 1
    assert len(sms.sent_otps) == 1
    assert sms.sent_otps[0]["telefone"] == "11987654321"
    cred = await cred_repo.buscar_por_identificador(
        "maria.silva@example.com", Role.PACIENTE.value
    )
    assert cred is not None
    assert cred.senha_hash.startswith("!UNUSABLE:")
    assert reader.pacientes is not None and len(reader.pacientes) == 1


@pytest.mark.asyncio
async def test_registrar_paciente_com_email_e_senha_cria_credencial() -> None:
    service, _, _, cred_repo, _, sms, session = _build_service()

    dados = RegistrarPacienteCommand(
        cpf="11144477735",
        nome_completo="João Pedro",
        data_nascimento=date(1988, 3, 10),
        telefone="11987654322",
        aceite_privacidade=True,
        email="Joao.Pedro@Example.com",
        senha="SenhaForte123",
    )
    out = await service.registrar_paciente(dados)

    assert out.otp_enviado is True
    assert session.commits == 1
    assert len(sms.sent_otps) == 1
    cred = await cred_repo.buscar_por_identificador(
        "joao.pedro@example.com", Role.PACIENTE.value
    )
    assert cred is not None
    assert cred.usuario_id == out.paciente_id
    assert cred.papel == Role.PACIENTE.value
    assert cred.mfa_ativo is False
    assert cred.senha_hash == "$argon2id$fake$SenhaForte123"


@pytest.mark.asyncio
async def test_registrar_paciente_validacoes_obrigatorias() -> None:
    service, _, _, _, _, _, _ = _build_service()

    with pytest.raises(ValidationError, match="aceite_privacidade=False"):
        await service.registrar_paciente(
            RegistrarPacienteCommand(
                cpf="11144477735",
                nome_completo="Maria",
                data_nascimento=date(1990, 1, 1),
                telefone="11987654321",
                email="maria@example.com",
                aceite_privacidade=False,
            ),
        )

    with pytest.raises(ValidationError, match="inválido"):
        await service.registrar_paciente(
            RegistrarPacienteCommand(
                cpf="11144477735",
                nome_completo="Maria",
                data_nascimento=date(1990, 1, 1),
                telefone="11987654321",
                email="email-invalido",
                aceite_privacidade=True,
            ),
        )

    with pytest.raises(ValidationError, match="mínimo de 8 caracteres"):
        await service.registrar_paciente(
            RegistrarPacienteCommand(
                cpf="11144477735",
                nome_completo="Maria",
                data_nascimento=date(1990, 1, 1),
                telefone="11987654321",
                email="maria@example.com",
                aceite_privacidade=True,
                senha="123",
            ),
        )


@pytest.mark.asyncio
async def test_registrar_paciente_duplicado_mascara_cpf_em_conflict() -> None:
    service, _, _, _, _, _, _ = _build_service()

    dados = RegistrarPacienteCommand(
        cpf="11144477735",
        nome_completo="Maria Silva",
        data_nascimento=date(1990, 1, 1),
        telefone="11987654321",
        email="maria.dup@example.com",
        aceite_privacidade=True,
    )
    await service.registrar_paciente(dados)

    with pytest.raises(ConflictError):
        await service.registrar_paciente(dados)

    with pytest.raises(ConflictError) as exc_info:
        await service.registrar_paciente(
            RegistrarPacienteCommand(
                cpf="11144477735",
                nome_completo="Maria Silva",
                data_nascimento=date(1990, 1, 1),
                telefone="11987654321",
                email="outra.maria@example.com",
                aceite_privacidade=True,
            ),
        )

    assert "111.***.***-35" not in exc_info.value.detail
    assert "11144477735" not in exc_info.value.detail
    assert "organização" not in exc_info.value.detail.lower()
    assert "entrar" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_identificar_paciente_por_cpf_e_email_sem_vazar_pii() -> None:
    service, _, writer, _, _, _, _ = _build_service(govbr_oidc_enabled=True)

    reg = await service.registrar_paciente(
        RegistrarPacienteCommand(
            cpf="11144477735",
            nome_completo="Ana Clara Souza",
            data_nascimento=date(1992, 7, 20),
            telefone="11987654321",
            aceite_privacidade=True,
            email="ana@example.com",
            senha="SenhaSegura123",
        ),
    )
    await writer.registrar_passkey_paciente(
        paciente_id=reg.paciente_id,
        credential_id="cred-1",
        public_key="pk",
    )

    by_cpf = await service.identificar_paciente(
        IdentificarPacienteCommand(
            identificador="111.444.777-35",
            client_ip="10.0.0.1",
        )
    )
    assert by_cpf.possui_conta is True
    assert by_cpf.telefone_mascarado == "1198****4321"
    assert by_cpf.govbr_habilitado is True
    assert set(by_cpf.metodos_disponiveis) == {"otp", "senha", "passkey", "govbr"}

    by_email = await service.identificar_paciente(
        IdentificarPacienteCommand(
            identificador="ANA@EXAMPLE.COM",
            client_ip="10.0.0.1",
        )
    )
    assert by_email.possui_conta is True
    assert by_email.telefone_mascarado == "1198****4321"
    assert set(by_email.metodos_disponiveis) == {"otp", "senha", "passkey", "govbr"}

    not_found = await service.identificar_paciente(
        IdentificarPacienteCommand(
            identificador="52998224725",
            client_ip="10.0.0.1",
        )
    )
    assert not_found.possui_conta is False
    assert not_found.telefone_mascarado is None
    assert not_found.metodos_disponiveis == ["govbr"]


@pytest.mark.asyncio
async def test_identificar_paciente_rate_limit_por_ip() -> None:
    service, _, _, _, _, _, _ = _build_service()

    for idx in range(15):
        await service.identificar_paciente(
            IdentificarPacienteCommand(
                identificador=f"user{idx}@example.com",
                client_ip="192.168.1.50",
            )
        )

    with pytest.raises(IdentificacaoRateLimitExcedidoError) as exc_info:
        await service.identificar_paciente(
            IdentificarPacienteCommand(
                identificador="extra@example.com",
                client_ip="192.168.1.50",
            )
        )
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_login_paciente_senha_sucesso_sem_mfa_e_lockout_apos_5_falhas() -> None:
    service, _, _, cred_repo, hasher, _, _ = _build_service()

    reg = await service.registrar_paciente(
        RegistrarPacienteCommand(
            cpf="11144477735",
            nome_completo="Carlos Lima",
            data_nascimento=date(1985, 2, 10),
            telefone="11987654321",
            aceite_privacidade=True,
            email="carlos@example.com",
            senha="SenhaCorreta123",
        ),
    )

    auth_ok = await service.autenticar_paciente_senha(
        LoginPacienteSenhaCommand(
            identificador="carlos@example.com",
            senha="SenhaCorreta123",
        ),
    )
    assert auth_ok.paciente_id == reg.paciente_id
    assert auth_ok.role == Role.PACIENTE.value
    claims = decode_access_token(auth_ok.access_token)
    assert claims.usuario_id == reg.paciente_id
    assert claims.papel == Role.PACIENTE.value

    auth_cpf = await service.autenticar_paciente_senha(
        LoginPacienteSenhaCommand(
            identificador="111.444.777-35",
            senha="SenhaCorreta123",
        ),
    )
    assert auth_cpf.paciente_id == reg.paciente_id

    for _ in range(4):
        with pytest.raises(CredenciaisInvalidasError):
            await service.autenticar_paciente_senha(
                LoginPacienteSenhaCommand(
                    identificador="carlos@example.com",
                    senha="Errada",
                ),
            )

    with pytest.raises(ContaBloqueadaError):
        await service.autenticar_paciente_senha(
            LoginPacienteSenhaCommand(
                identificador="carlos@example.com",
                senha="Errada",
            ),
        )

    prev_dummy_locked = hasher.dummy_calls
    with pytest.raises(ContaBloqueadaError):
        await service.autenticar_paciente_senha(
            LoginPacienteSenhaCommand(
                identificador="carlos@example.com",
                senha="SenhaCorreta123",
            ),
        )
    assert hasher.dummy_calls == prev_dummy_locked + 1

    prev_dummy = hasher.dummy_calls
    with pytest.raises(CredenciaisInvalidasError):
        await service.autenticar_paciente_senha(
            LoginPacienteSenhaCommand(
                identificador="naoexiste@example.com",
                senha="123",
            ),
        )
    assert hasher.dummy_calls == prev_dummy + 1

    cred = await cred_repo.buscar_por_identificador(
        "carlos@example.com", Role.PACIENTE.value
    )
    assert cred is not None
    cred.desativar()
    with pytest.raises(ContaDesativadaError):
        await service.autenticar_paciente_senha(
            LoginPacienteSenhaCommand(
                identificador="carlos@example.com",
                senha="SenhaCorreta123",
            ),
        )


def test_obter_capacidades_metodos() -> None:
    service_off, _, _, _, _, _, _ = _build_service(govbr_oidc_enabled=False)
    caps_off = service_off.obter_capacidades_metodos()
    assert caps_off.govbr_oidc_enabled is False
    assert caps_off.passkeys_enabled is True
    assert caps_off.otp_enabled is True
    assert caps_off.password_fallback_enabled is True

    service_on, _, _, _, _, _, _ = _build_service(govbr_oidc_enabled=True)
    caps_on = service_on.obter_capacidades_metodos()
    assert caps_on.govbr_oidc_enabled is True


@pytest.mark.asyncio
async def test_registrar_apenas_email_ou_apenas_senha() -> None:
    service, reader, _, cred_repo, hasher, _, _ = _build_service()

    reg_email = await service.registrar_paciente(
        RegistrarPacienteCommand(
            cpf="11144477735",
            nome_completo="Paciente Sem Senha",
            data_nascimento=date(1991, 4, 1),
            telefone="11987654321",
            aceite_privacidade=True,
            email="sem.senha@example.com",
        ),
    )
    cred_email = await cred_repo.buscar_por_identificador(
        "sem.senha@example.com", Role.PACIENTE.value
    )
    assert cred_email is not None
    assert cred_email.usuario_id == reg_email.paciente_id

    id_email = await service.identificar_paciente(
        IdentificarPacienteCommand(
            identificador="sem.senha@example.com",
            client_ip="10.0.0.2",
        )
    )
    assert id_email.possui_conta is True
    assert id_email.metodos_disponiveis == ["otp"]

    prev_dummy = hasher.dummy_calls
    with pytest.raises(CredenciaisInvalidasError):
        await service.autenticar_paciente_senha(
            LoginPacienteSenhaCommand(
                identificador="sem.senha@example.com",
                senha="QualquerSenha123",
            ),
        )
    assert hasher.dummy_calls == prev_dummy + 1

    reg_cpf = await service.registrar_paciente(
        RegistrarPacienteCommand(
            cpf="52998224725",
            nome_completo="Paciente Com Senha",
            data_nascimento=date(1989, 8, 22),
            telefone="11987654399",
            email="paciente.senha@example.com",
            aceite_privacidade=True,
            senha="MinhaSenha99",
        ),
    )
    cred_cpf = await cred_repo.buscar_por_identificador(
        "paciente.senha@example.com", Role.PACIENTE.value
    )
    assert cred_cpf is not None
    assert cred_cpf.usuario_id == reg_cpf.paciente_id

    id_cpf = await service.identificar_paciente(
        IdentificarPacienteCommand(
            identificador="52998224725",
            client_ip="10.0.0.3",
        )
    )
    assert id_cpf.possui_conta is True
    assert set(id_cpf.metodos_disponiveis) == {"otp", "senha"}

    before_count = len(reader.pacientes or [])
    with pytest.raises(ConflictError):
        await service.registrar_paciente(
            RegistrarPacienteCommand(
                cpf="39053344705",
                nome_completo="Outro Paciente",
                data_nascimento=date(1995, 1, 1),
                telefone="11987654300",
                aceite_privacidade=True,
                email="sem.senha@example.com",
            ),
        )
    assert len(reader.pacientes or []) == before_count

    service_prod, _, _, _, _, _, _ = _build_service(expose_debug_otp=False)
    out_prod = await service_prod.registrar_paciente(
        RegistrarPacienteCommand(
            cpf="39053344705",
            nome_completo="Paciente Prod",
            data_nascimento=date(1995, 1, 1),
            telefone="11987654300",
            email="prod.paciente@example.com",
            aceite_privacidade=True,
        ),
    )
    assert out_prod.codigo_debug is None


@pytest.mark.asyncio
async def test_patient_hybrid_http_router_endpoints_asgi() -> None:
    """Exercise all 4 FastAPI router endpoints and RFC 7807 error mapping in memory."""
    from src.main import app
    from src.modules.auth.composition import get_patient_auth_service

    service, _, _, _, _, _, _ = _build_service(govbr_oidc_enabled=True)
    app.dependency_overrides[get_patient_auth_service] = lambda: service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_methods = await client.get("/api/v1/auth/patient/methods")
            assert resp_methods.status_code == 200
            assert resp_methods.json() == {
                "govbr_oidc_enabled": True,
                "passkeys_enabled": True,
                "otp_enabled": True,
                "password_fallback_enabled": True,
            }

            resp_reg = await client.post(
                "/api/v1/auth/patient/register",
                json={
                    "cpf": "111.444.777-35",
                    "nome_completo": "Helena Dias",
                    "data_nascimento": "1994-11-05",
                    "telefone": "11987654321",
                    "aceite_privacidade": True,
                    "email": "helena@example.com",
                    "senha": "SenhaValida123",
                },
            )
            assert resp_reg.status_code == 201
            reg_body = resp_reg.json()
            assert reg_body["telefone_mascarado"] == "1198****4321"
            assert reg_body["otp_enviado"] is True
            assert reg_body["expira_em_segundos"] == 300
            assert reg_body["codigo_debug"] is not None
            assert len(reg_body["codigo_debug"]) == 6

            resp_id = await client.post(
                "/api/v1/auth/patient/identify",
                json={"identificador": "helena@example.com"},
            )
            assert resp_id.status_code == 200
            id_body = resp_id.json()
            assert id_body["possui_conta"] is True
            assert id_body["govbr_habilitado"] is True
            assert set(id_body["metodos_disponiveis"]) == {"otp", "senha", "govbr"}

            resp_pwd = await client.post(
                "/api/v1/auth/patient/login-password",
                json={
                    "identificador": "helena@example.com",
                    "senha": "SenhaValida123",
                },
            )
            assert resp_pwd.status_code == 200
            pwd_body = resp_pwd.json()
            assert pwd_body["paciente_id"] == reg_body["paciente_id"]
            assert pwd_body["role"] == "PACIENTE"
            assert pwd_body["access_token"]
    finally:
        app.dependency_overrides.pop(get_patient_auth_service, None)


def test_identity_writer_integrity_error_classification() -> None:
    """FK violation (23503) must NOT falsely report duplicate CPF ConflictError."""
    from src.modules.identity.infrastructure.identity_writer_sql import (
        _translate_patient_integrity_error,  # pyright: ignore[reportPrivateUsage]
    )

    fk_exc = IntegrityError(
        "INSERT INTO pacientes",
        {},
        SimpleNamespace(
            sqlstate="23503",
            diag=SimpleNamespace(constraint_name="fk_pacientes_ref"),
        ),  # type: ignore[arg-type]
    )
    fk_err = _translate_patient_integrity_error(fk_exc, cpf="11144477735")
    assert isinstance(fk_err, NotFoundError)
    assert "cpf" not in fk_err.detail.lower()
    assert "fk_pacientes_ref" in fk_err.detail

    uniq_exc = IntegrityError(
        "INSERT INTO pacientes",
        {},
        SimpleNamespace(
            sqlstate="23505",
            diag=SimpleNamespace(constraint_name="uq_paciente_cpf"),
        ),  # type: ignore[arg-type]
    )
    uniq_err = _translate_patient_integrity_error(uniq_exc, cpf="11144477735")
    assert isinstance(uniq_err, ConflictError)
    assert "11144477735" not in uniq_err.detail
    assert "111.***.***-35" not in uniq_err.detail
    assert "organização" not in uniq_err.detail.lower()
    assert "entrar" in uniq_err.detail.lower()

    other_exc = IntegrityError(
        "INSERT INTO pacientes",
        {},
        SimpleNamespace(sqlstate="23514", diag=SimpleNamespace(constraint_name="chk")),  # type: ignore[arg-type]
    )
    other_err = _translate_patient_integrity_error(other_exc, cpf="11144477735")
    assert isinstance(other_err, ValidationError)


@pytest.mark.asyncio
async def test_registrar_e_login_exigem_session_nao_nula() -> None:
    """Métodos persistentes devem falhar rápido quando session=None."""
    reader = FakeIdentityReader(pacientes=[])
    settings = get_settings()
    service = PatientAuthService(
        token_service=JWTTokenService(
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            access_token_expire_minutes=15,
        ),
        challenge_store=MemoryChallengeStore(),
        rate_limiter=FakeAuthRateLimiter(),
        identity_reader=reader,
        identity_writer=FakeIdentityWriter(reader),
        credential_repo=FakePatientCredentialRepository(),
        password_hasher=FakePasswordHasher(),
        session=None,
    )

    with pytest.raises(ValueError, match="AsyncSession"):
        await service.registrar_paciente(
            RegistrarPacienteCommand(
                cpf="11144477735",
                nome_completo="Maria",
                data_nascimento=date(1990, 1, 1),
                telefone="11987654321",
                email="maria@example.com",
                aceite_privacidade=True,
            )
        )

    with pytest.raises(ValueError, match="AsyncSession"):
        await service.autenticar_paciente_senha(
            LoginPacienteSenhaCommand(
                identificador="maria@example.com",
                senha="Senha123",
            )
        )


@pytest.mark.asyncio
async def test_registrar_paciente_rate_limit_por_ip_antes_duplicidade_e_hash() -> None:
    """Rate limit por IP em registrar_paciente bloqueia antes de DB e Argon2id."""
    service, _, _, cred_repo, hasher, _, _ = _build_service()

    for idx in range(10):
        with pytest.raises(ValidationError):
            await service.registrar_paciente(
                RegistrarPacienteCommand(
                    cpf="11144477735",
                    nome_completo=f"User {idx}",
                    data_nascimento=date(1990, 1, 1),
                    telefone="11987654321",
                    email=f"user{idx}@example.com",
                    aceite_privacidade=False,
                    client_ip="10.20.30.40",
                )
            )

    prev_existe = len(cred_repo.existe_calls)
    prev_hash = hasher.hash_calls
    with pytest.raises(IdentificacaoRateLimitExcedidoError) as exc_info:
        await service.registrar_paciente(
            RegistrarPacienteCommand(
                cpf="11144477735",
                nome_completo="Bloqueado",
                data_nascimento=date(1990, 1, 1),
                telefone="11987654321",
                email="bloqueado@example.com",
                aceite_privacidade=True,
                senha="SenhaValida123",
                client_ip="10.20.30.40",
            )
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers
    assert len(cred_repo.existe_calls) == prev_existe
    assert hasher.hash_calls == prev_hash


@pytest.mark.asyncio
async def test_registrar_paciente_conflito_com_senha_executa_dummy_verify() -> None:
    """Conflito de e-mail com senha informada deve executar dummy_verify."""
    service, _, _, _, hasher, _, _ = _build_service()

    await service.registrar_paciente(
        RegistrarPacienteCommand(
            cpf="11144477735",
            nome_completo="Maria Silva",
            data_nascimento=date(1990, 1, 1),
            telefone="11987654321",
            email="maria.timing@example.com",
            aceite_privacidade=True,
            senha="SenhaValida123",
        )
    )

    prev_dummy = hasher.dummy_calls
    with pytest.raises(ConflictError):
        await service.registrar_paciente(
            RegistrarPacienteCommand(
                cpf="52998224725",
                nome_completo="Outra Pessoa",
                data_nascimento=date(1991, 2, 2),
                telefone="11987654322",
                email="maria.timing@example.com",
                aceite_privacidade=True,
                senha="OutraSenha123",
            )
        )
    assert hasher.dummy_calls == prev_dummy + 1


@pytest.mark.asyncio
async def test_login_paciente_nao_reseta_rate_limit_ip_e_retorna_429() -> None:
    """Sucesso no login não reseta rate limit por IP e retorna 429 Retry-After."""
    service, _, _, _, _, _, _ = _build_service()

    await service.registrar_paciente(
        RegistrarPacienteCommand(
            cpf="11144477735",
            nome_completo="Carlos Lima",
            data_nascimento=date(1985, 2, 10),
            telefone="11987654321",
            aceite_privacidade=True,
            email="carlos.rl@example.com",
            senha="SenhaCorreta123",
        )
    )

    for idx in range(14):
        with pytest.raises(CredenciaisInvalidasError):
            await service.autenticar_paciente_senha(
                LoginPacienteSenhaCommand(
                    identificador=f"inexistente{idx}@example.com",
                    senha="Errada",
                    client_ip="198.51.100.7",
                )
            )

    ok = await service.autenticar_paciente_senha(
        LoginPacienteSenhaCommand(
            identificador="carlos.rl@example.com",
            senha="SenhaCorreta123",
            client_ip="198.51.100.7",
        )
    )
    assert ok.access_token

    with pytest.raises(IdentificacaoRateLimitExcedidoError) as exc_info:
        await service.autenticar_paciente_senha(
            LoginPacienteSenhaCommand(
                identificador="carlos.rl@example.com",
                senha="SenhaCorreta123",
                client_ip="198.51.100.7",
            )
        )
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers


@pytest.mark.asyncio
async def test_login_paciente_helper_nao_commita_e_falha_commita_no_service() -> None:
    """Helper _verify_patient_password_or_lockout não commita; service commita."""
    service, _, _, cred_repo, _, _, session = _build_service()

    await service.registrar_paciente(
        RegistrarPacienteCommand(
            cpf="11144477735",
            nome_completo="Ana Paula",
            data_nascimento=date(1990, 5, 10),
            telefone="11987654321",
            aceite_privacidade=True,
            email="ana.commit@example.com",
            senha="SenhaCorreta123",
        )
    )
    cred = await cred_repo.buscar_por_identificador(
        "ana.commit@example.com", Role.PACIENTE.value
    )
    assert cred is not None

    commits_before_helper = session.commits
    outcome = await service._verify_patient_password_or_lockout(cred, "Errada")  # pyright: ignore[reportPrivateUsage]
    assert outcome == "invalid"
    assert session.commits == commits_before_helper

    cred.falhas_login_consecutivas = 0
    cred.bloqueado_ate = None
    with pytest.raises(CredenciaisInvalidasError):
        await service.autenticar_paciente_senha(
            LoginPacienteSenhaCommand(
                identificador="ana.commit@example.com",
                senha="Errada",
            )
        )
    assert session.commits == commits_before_helper + 1

    cred.bloqueado_ate = datetime.now(UTC) + timedelta(minutes=10)
    prev_dummy = service._password_hasher.dummy_calls  # type: ignore[union-attr]  # pyright: ignore[reportPrivateUsage,reportAttributeAccessIssue]
    with pytest.raises(ContaBloqueadaError):
        await service.autenticar_paciente_senha(
            LoginPacienteSenhaCommand(
                identificador="ana.commit@example.com",
                senha="SenhaCorreta123",
            )
        )
    assert service._password_hasher.dummy_calls == prev_dummy + 1  # type: ignore[union-attr]  # pyright: ignore[reportPrivateUsage,reportAttributeAccessIssue]


@pytest.mark.asyncio
async def test_login_paciente_cpf_validacao_e_sem_query_duplicada() -> None:
    """CPF inválido falha em validate_cpf e CPF válido vai direto a CADSUS."""
    service, reader, _, cred_repo, _, _, _ = _build_service()

    await service.registrar_paciente(
        RegistrarPacienteCommand(
            cpf="111.444.777-35",
            nome_completo="Pedro CPF",
            data_nascimento=date(1988, 7, 15),
            telefone="11987654321",
            aceite_privacidade=True,
            email="pedro.cpf@example.com",
            senha="SenhaCorreta123",
        )
    )

    lookups_before = len(reader.lookups)
    with pytest.raises(ValidationError):
        await service.autenticar_paciente_senha(
            LoginPacienteSenhaCommand(
                identificador="12345678900",
                senha="SenhaCorreta123",
            )
        )
    assert len(reader.lookups) == lookups_before

    ident_lookups_before = len(cred_repo.identificador_lookups)
    res = await service.autenticar_paciente_senha(
        LoginPacienteSenhaCommand(
            identificador="111.444.777-35",
            senha="SenhaCorreta123",
        )
    )
    assert res.access_token
    assert len(cred_repo.identificador_lookups) == ident_lookups_before


def test_patient_credential_repository_integrity_error_classification() -> None:
    """SqlPatientCredentialRepository discrimina 23505, 23503 e demais SQLSTATE."""
    from src.modules.auth.infrastructure.patient_credential_repository_sql import (
        _translate_credential_integrity_error,  # pyright: ignore[reportPrivateUsage]
    )

    uniq_exc = IntegrityError(
        "INSERT INTO usuarios_credenciais",
        {},
        SimpleNamespace(
            sqlstate="23505",
            diag=SimpleNamespace(
                constraint_name="uq_usuarios_credenciais_identificador"
            ),
        ),  # type: ignore[arg-type]
    )
    uniq_err = _translate_credential_integrity_error(uniq_exc)
    assert isinstance(uniq_err, ConflictError)
    assert "entrar" in uniq_err.detail.lower()

    fk_exc = IntegrityError(
        "INSERT INTO usuarios_credenciais",
        {},
        SimpleNamespace(
            sqlstate="23503",
            diag=SimpleNamespace(constraint_name="fk_credenciais_ref"),
        ),  # type: ignore[arg-type]
    )
    fk_err = _translate_credential_integrity_error(fk_exc)
    assert isinstance(fk_err, NotFoundError)
    assert "fk_credenciais_ref" in fk_err.detail

    other_exc = IntegrityError(
        "INSERT INTO usuarios_credenciais",
        {},
        SimpleNamespace(sqlstate="23514", diag=SimpleNamespace(constraint_name="chk")),  # type: ignore[arg-type]
    )
    other_err = _translate_credential_integrity_error(other_exc)
    assert isinstance(other_err, ValidationError)
    assert "23514" in other_err.detail


@pytest.mark.asyncio
async def test_identity_writer_normalizes_cpf_before_precheck() -> None:
    """SqlIdentityWriter.criar_paciente deve normalizar CPF antes da pré-consulta."""
    from src.modules.identity.infrastructure.identity_writer_sql import (
        SqlIdentityWriter,
    )

    executed_stmts: list[object] = []

    class _CapturingSession(FakeAsyncSession):
        async def execute(self, *args: object, **kwargs: object) -> object:
            executed_stmts.append(args[0])
            return await super().execute(*args, **kwargs)

    session = _CapturingSession()
    writer = SqlIdentityWriter(session=cast("AsyncSession", session))
    created = await writer.criar_paciente(
        cpf="111.444.777-35",
        nome_completo="Paciente Normalizado",
        data_nascimento=date(1990, 1, 1),
        telefone="11987654321",
    )
    assert created.cpf == "11144477735"
    assert len(executed_stmts) == 1
    compiled = str(
        executed_stmts[0].compile(compile_kwargs={"literal_binds": True})  # type: ignore[attr-defined]
    )
    assert "11144477735" in compiled
    assert "111.444.777-35" not in compiled


def test_composition_hardening_and_identity_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Composition injeta rate_limiter, oculta debug OTP em prod e limpa dead deps."""
    from src.modules.auth import composition as auth_comp
    from src.modules.auth.infrastructure.valkey_rate_limiter import FakeAuthRateLimiter
    from src.modules.identity import composition as identity_comp

    assert not hasattr(identity_comp, "get_identity_writer")
    assert not hasattr(identity_comp, "IdentityWriterDep")

    monkeypatch.setattr(
        auth_comp,
        "get_settings",
        lambda: CommonSettings(
            ENVIRONMENT="production",
            DEBUG=True,
            RATE_LIMIT_BACKEND="memory",
        ),
    )
    session = cast("AsyncSession", FakeAsyncSession())
    service = auth_comp.build_patient_auth_service_for_session(session=session)
    assert service._expose_debug_otp is False  # pyright: ignore[reportPrivateUsage]
    assert isinstance(service._rate_limiter, FakeAuthRateLimiter)  # pyright: ignore[reportPrivateUsage]
