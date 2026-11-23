"""Unit tests for Tripartite Authentication and TOTP MFA (RFC 6238).

Regras: ADR-007, ADR-013, RF-01, CFM nº 2.454/2026, CFM nº 2.314/2022.
"""

import asyncio
from datetime import date
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from src.core.authz import (
    BearerAuthSettings,
    get_current_user,
    get_mfa_setup_or_access_user,
)
from src.core.authz.revocation import MemoryTokenRevocation
from src.core.authz.roles import Role
from src.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from src.core.uuid7 import uuid7
from src.modules.auth.application.dtos import (
    LoginCommand,
    RateLimitResultDTO,
)
from src.modules.auth.application.ports.auth_rate_limiter_port import (
    AuthRateLimiterPort,
)
from src.modules.auth.application.ports.doctor_presence_port import (
    DoctorPresencePort,
)
from src.modules.auth.application.ports.identity_reader_port import (
    PacienteAuthLookupData,
)
from src.modules.auth.application.services.auth_service import AuthService
from src.modules.auth.application.services.patient_auth_service import (
    PatientAuthService,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.auth.domain.exceptions import (
    CredenciaisInvalidasError,
    MfaCodigoInvalidoError,
    PacienteNaoEncontradoError,
    TokenRevogadoError,
)
from src.modules.auth.domain.models import UsuarioCredencial
from src.modules.auth.domain.totp import (
    build_totp_uri,
    generate_totp_code,
    generate_totp_secret,
    verify_totp_code,
)
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService

from tests.doubles import (
    FakeAsyncSession,
    FakeIdentityReader,
    FakePasswordHasher,
    FakeResult,
    MemoryChallengeStore,
)


class FakeAuthRateLimiter(AuthRateLimiterPort):
    """Named fake implementation of AuthRateLimiterPort."""

    def __init__(self, permitido: bool = True) -> None:
        self.permitido = permitido
        self.reset_keys: list[str] = []

    async def verificar_e_incrementar(
        self,
        chave: str,
        limite: int = 5,
        janela_segundos: int = 900,
    ) -> RateLimitResultDTO:
        return RateLimitResultDTO(
            permitido=self.permitido,
            tentativas_restantes=limite - 1,
            retry_after_segundos=0 if self.permitido else 900,
        )

    async def resetar(self, chave: str) -> None:
        self.reset_keys.append(chave)


TEST_JWT_SECRET = "super-secret-key-for-testing-purposes-123456"


def _make_credencial(
    usuario_id: UUID | None = None,
    identificador: str = "dr.silva@medisync.com",
    senha_pura: str = "senha123",
    papel: str = "MEDICO",
    mfa_secret: str | None = None,
    mfa_ativo: bool = False,
) -> UsuarioCredencial:
    return UsuarioCredencial(
        usuario_id=usuario_id or uuid7(),
        identificador=identificador,
        senha_hash=f"$argon2id$fake${senha_pura}",
        papel=papel,
        mfa_secret=mfa_secret,
        mfa_ativo=mfa_ativo,
    )


def _make_auth_service(
    session: FakeAsyncSession,
    token_service: JWTTokenService | None = None,
    hasher: FakePasswordHasher | None = None,
    revocation: MemoryTokenRevocation | None = None,
    doctor_presence: DoctorPresencePort | None = None,
) -> AuthService:
    return AuthService(
        session=cast("AsyncSession", session),
        hasher=hasher or FakePasswordHasher(),
        token_service=token_service or JWTTokenService(secret_key=TEST_JWT_SECRET),
        rate_limiter=FakeAuthRateLimiter(),
        revocation=revocation or MemoryTokenRevocation(),
        doctor_presence=doctor_presence,
    )


def test_totp_generation_and_verification() -> None:
    """Valida geração de segredo Base32, código de 6 dígitos e validação RFC 6238."""
    secret = generate_totp_secret()
    assert len(secret) == 32
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)

    code = generate_totp_code(secret)
    assert len(code) == 6
    assert code.isdigit()

    assert verify_totp_code(secret, code) is True
    assert verify_totp_code(secret, "000000") is False
    assert verify_totp_code(secret, "abcdef") is False
    assert verify_totp_code(secret, "") is False


@pytest.mark.asyncio
async def test_mfa_login_e_logout_sincronizam_presenca_medico_ativo() -> None:
    """MFA verify registers MEDICO in DoctorPresencePort and logout unregisters."""
    from tests.doubles import FakeQueueEngine

    medico_id = uuid7()
    secret = generate_totp_secret()
    cred = _make_credencial(
        usuario_id=medico_id,
        papel="MEDICO",
        mfa_secret=secret,
        mfa_ativo=True,
    )
    engine = FakeQueueEngine()
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    temp_token = token_svc.gerar_mfa_token(usuario_id=medico_id, papel="MEDICO")
    session = FakeAsyncSession(results=[FakeResult(cred)])
    service = _make_auth_service(
        session, token_service=token_svc, doctor_presence=engine
    )

    pair = await service.verificar_mfa_login(temp_token, generate_totp_code(secret))
    assert medico_id in engine.medicos_ativos

    await service.revogar_sessao(
        refresh_token=pair.refresh_token,
        access_token=pair.access_token,
    )
    assert medico_id not in engine.medicos_ativos


def test_totp_uri_building() -> None:
    """Valida geração de URI compatível com Google Authenticator."""
    secret = "JBSWY3DPEHPK3PXP"
    uri = build_totp_uri(secret, "medico@clinica.com", issuer="MediSync")
    assert uri.startswith("otpauth://totp/MediSync:medico%40clinica.com?")
    assert "secret=JBSWY3DPEHPK3PXP" in uri
    assert "issuer=MediSync" in uri
    assert "digits=6" in uri


@pytest.mark.asyncio
async def test_gerar_mfa_secret_sucesso() -> None:
    """Valida setup de MFA retornando segredo Base32 e URI otpauth."""
    cred = _make_credencial()
    session = FakeAsyncSession(results=[FakeResult(cred)])
    service = _make_auth_service(session)

    setup_dto = await service.gerar_mfa_secret(usuario_id=cred.usuario_id)

    assert len(setup_dto.secret) == 32
    assert setup_dto.uri.startswith("otpauth://totp/MediSync:")
    assert cred.mfa_secret == setup_dto.secret
    assert session.commits == 1


@pytest.mark.asyncio
async def test_gerar_mfa_secret_usuario_nao_encontrado() -> None:
    """Valida erro 404 ao solicitar setup de MFA para usuário inexistente."""
    session = FakeAsyncSession(results=[FakeResult(None)])
    service = _make_auth_service(session)

    uid = uuid4()
    with pytest.raises(NotFoundError) as exc_info:
        await service.gerar_mfa_secret(usuario_id=uid)

    assert str(uid) in str(exc_info.value)


@pytest.mark.asyncio
async def test_ativar_mfa_codigo_invalido_rejeitado() -> None:
    """Valida rejeição com 401 quando o código TOTP não confere."""
    secret = generate_totp_secret()
    cred = _make_credencial(mfa_secret=secret, mfa_ativo=False)
    session = FakeAsyncSession(results=[FakeResult(cred)])
    service = _make_auth_service(session)

    with pytest.raises(MfaCodigoInvalidoError) as exc_info:
        await service.ativar_mfa(
            usuario_id=cred.usuario_id,
            codigo="000000",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "MFA_CODIGO_INVALIDO"
    assert "000000" in exc_info.value.detail
    assert cred.mfa_ativo is False


@pytest.mark.asyncio
async def test_ativar_mfa_sucesso() -> None:
    """Valida ativação definitiva do MFA com código TOTP válido."""
    secret = generate_totp_secret()
    cred = _make_credencial(mfa_secret=secret, mfa_ativo=False)
    session = FakeAsyncSession(results=[FakeResult(cred)])
    service = _make_auth_service(session)

    valid_code = generate_totp_code(secret)
    sucesso = await service.ativar_mfa(
        usuario_id=cred.usuario_id,
        codigo=valid_code,
    )

    assert sucesso is True
    assert cred.mfa_ativo is True
    assert session.commits == 1


@pytest.mark.asyncio
async def test_autenticar_medico_mfa_ativo_exige_segundo_fator() -> None:
    """Médico com MFA ativo recebe token temporário com mfa_requerido=True."""
    secret = generate_totp_secret()
    cred = _make_credencial(
        papel="MEDICO",
        senha_pura="senha123",
        mfa_secret=secret,
        mfa_ativo=True,
    )
    session = FakeAsyncSession(results=[FakeResult(cred)])
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    service = _make_auth_service(session, token_service=token_svc)

    cmd = LoginCommand(
        identificador=cred.identificador,
        senha="senha123",
        client_ip="127.0.0.1",
    )
    tokens = await service.autenticar(cmd)

    assert tokens.mfa_requerido is True
    assert tokens.mfa_setup_requerido is False
    assert tokens.refresh_token == ""
    assert tokens.access_token is not None

    payload = token_svc.validar_mfa_token(tokens.access_token)
    assert payload.sub == cred.usuario_id
    assert not hasattr(payload, "org_id")
    assert payload.mfa_pending is True


@pytest.mark.asyncio
async def test_autenticar_medico_mfa_inativo_exige_mfa_setup_requerido() -> None:
    """Médico com MFA inativo recebe token temporário."""
    cred = _make_credencial(
        papel="MEDICO",
        senha_pura="senha123",
        mfa_secret=None,
        mfa_ativo=False,
    )
    session = FakeAsyncSession(results=[FakeResult(cred)])
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    service = _make_auth_service(session, token_service=token_svc)

    cmd = LoginCommand(
        identificador=cred.identificador,
        senha="senha123",
        client_ip="127.0.0.1",
    )
    tokens = await service.autenticar(cmd)

    assert tokens.mfa_requerido is True
    assert tokens.mfa_setup_requerido is True
    assert tokens.refresh_token == ""
    assert tokens.access_token is not None

    payload = token_svc.validar_mfa_token(tokens.access_token)
    assert payload.sub == cred.usuario_id
    assert not hasattr(payload, "org_id")
    assert payload.mfa_pending is True


@pytest.mark.asyncio
async def test_autenticar_gestor_mfa_inativo_exige_mfa_setup_requerido() -> None:
    """Gestor com MFA inativo recebe token temporário exigindo setup."""
    cred = _make_credencial(
        papel="GESTOR_UNIDADE",
        senha_pura="senha123",
        mfa_secret=None,
        mfa_ativo=False,
    )
    session = FakeAsyncSession(results=[FakeResult(cred)])
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    service = _make_auth_service(session, token_service=token_svc)

    cmd = LoginCommand(
        identificador=cred.identificador,
        senha="senha123",
        client_ip="127.0.0.1",
    )
    tokens = await service.autenticar(cmd)

    assert tokens.mfa_requerido is True
    assert tokens.mfa_setup_requerido is True
    assert tokens.refresh_token == ""
    assert tokens.access_token is not None

    payload = token_svc.validar_mfa_token(tokens.access_token)
    assert payload.sub == cred.usuario_id
    assert not hasattr(payload, "org_id")
    assert payload.mfa_pending is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "papel",
    [
        "MEDICO",
        "GESTOR_UNIDADE",
    ],
)
async def test_roles_requiring_mfa_bloqueiam_acesso_direto(papel: str) -> None:
    """Todas as funções em ROLES_REQUIRING_MFA exigem MFA mesmo sem ter ativado."""
    cred = _make_credencial(
        papel=papel,
        senha_pura="senha123",
        mfa_ativo=False,
    )
    session = FakeAsyncSession(results=[FakeResult(cred)])
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    service = _make_auth_service(session, token_service=token_svc)

    cmd = LoginCommand(
        identificador=cred.identificador,
        senha="senha123",
        client_ip="127.0.0.1",
    )
    tokens = await service.autenticar(cmd)
    assert tokens.mfa_requerido is True
    assert tokens.mfa_setup_requerido is True


@pytest.mark.asyncio
async def test_verificar_mfa_login_sucesso() -> None:
    """Validação do segundo fator TOTP emite tokens definitivos de sessão."""
    secret = generate_totp_secret()
    cred = _make_credencial(
        papel="MEDICO",
        senha_pura="senha123",
        mfa_secret=secret,
        mfa_ativo=True,
    )
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    temp_token = token_svc.gerar_mfa_token(
        usuario_id=cred.usuario_id,
        papel=cred.papel,
    )

    session = FakeAsyncSession(results=[FakeResult(cred)])
    service = _make_auth_service(session, token_service=token_svc)

    valid_code = generate_totp_code(secret)
    final_tokens = await service.verificar_mfa_login(
        temp_token=temp_token,
        codigo=valid_code,
    )

    assert final_tokens.mfa_requerido is False
    assert final_tokens.access_token is not None
    assert final_tokens.refresh_token != ""

    dec = token_svc.validar_access_token(final_tokens.access_token)
    assert dec.sub == cred.usuario_id
    assert dec.papel == "MEDICO"
    assert dec.mfa_pending is False


@pytest.mark.asyncio
async def test_verificar_mfa_login_codigo_incorreto_rejeitado() -> None:
    """Validação com código incorreto no 2º fator levanta erro 401."""
    secret = generate_totp_secret()
    cred = _make_credencial(
        papel="MEDICO",
        senha_pura="senha123",
        mfa_secret=secret,
        mfa_ativo=True,
    )
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    temp_token = token_svc.gerar_mfa_token(
        usuario_id=cred.usuario_id,
        papel=cred.papel,
    )

    session = FakeAsyncSession(results=[FakeResult(cred)])
    service = _make_auth_service(session, token_service=token_svc)

    with pytest.raises(MfaCodigoInvalidoError) as exc_info:
        await service.verificar_mfa_login(
            temp_token=temp_token,
            codigo="000000",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "MFA_CODIGO_INVALIDO"


@pytest.mark.asyncio
async def test_autenticar_cadsus_govbr_sucesso() -> None:
    """CADSUS/Gov.br desambigua por CPF + nascimento + 2º fator civil."""
    paciente_id = uuid7()
    lookup_paciente = PacienteAuthLookupData(
        id=paciente_id,
        telefone="11987654321",
        cpf="11144477735",
        nome_completo="Carlos Paciente",
        nome_mae="Maria Paciente",
        data_nascimento=date(1990, 5, 15),
    )
    fake_reader = FakeIdentityReader(paciente=lookup_paciente)
    service = PatientAuthService(
        token_service=JWTTokenService(
            secret_key=TEST_JWT_SECRET, access_token_expire_minutes=15
        ),
        challenge_store=MemoryChallengeStore(),
        rate_limiter=FakeAuthRateLimiter(),
        identity_reader=fake_reader,
    )

    resultado = await service.autenticar_cadsus_govbr(
        cpf="11144477735",
        data_nascimento=date(1990, 5, 15),
        nome_mae="Maria Paciente",
    )

    assert resultado.paciente_id == paciente_id
    assert resultado.role == "PACIENTE"
    assert resultado.token_type == "bearer"
    assert resultado.expires_in == 900
    assert resultado.access_token is not None


@pytest.mark.asyncio
async def test_autenticar_cadsus_govbr_paciente_nao_encontrado() -> None:
    """Falha de desambiguação CADSUS levanta PacienteNaoEncontradoError."""
    fake_reader = FakeIdentityReader(paciente=None)
    service = PatientAuthService(
        token_service=JWTTokenService(
            secret_key=TEST_JWT_SECRET, access_token_expire_minutes=15
        ),
        challenge_store=MemoryChallengeStore(),
        rate_limiter=FakeAuthRateLimiter(),
        identity_reader=fake_reader,
    )

    with pytest.raises(PacienteNaoEncontradoError) as exc_info:
        await service.autenticar_cadsus_govbr(
            cpf="11144477735",
            data_nascimento=date(1990, 5, 15),
            nome_mae="Maria Paciente",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "PACIENTE_NAO_ENCONTRADO"


@pytest.mark.asyncio
async def test_verificar_mfa_login_exige_mfa_ativo_true() -> None:
    """temp_token não pode autenticar em /mfa/verify antes de /mfa/activate."""
    secret = generate_totp_secret()
    cred = _make_credencial(
        papel="MEDICO",
        senha_pura="senha123",
        mfa_secret=secret,
        mfa_ativo=False,
    )
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    temp_token = token_svc.gerar_mfa_token(
        usuario_id=cred.usuario_id,
        papel=cred.papel,
    )
    service = _make_auth_service(
        FakeAsyncSession(results=[FakeResult(cred)]),
        token_service=token_svc,
    )

    with pytest.raises(CredenciaisInvalidasError):
        await service.verificar_mfa_login(
            temp_token=temp_token,
            codigo=generate_totp_code(secret),
        )


@pytest.mark.asyncio
async def test_verificar_mfa_login_uso_unico_bloqueia_replay_e_pre_revogado() -> None:
    """temp_token MFA tem uso único atômico: 2ª tentativa levanta TokenRevogadoError."""
    secret = generate_totp_secret()
    cred = _make_credencial(
        papel="GESTOR_UNIDADE",
        senha_pura="senha123",
        mfa_secret=secret,
        mfa_ativo=True,
    )
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    temp_token = token_svc.gerar_mfa_token(
        usuario_id=cred.usuario_id,
        papel=cred.papel,
    )
    revocation = MemoryTokenRevocation()
    service = _make_auth_service(
        FakeAsyncSession(results=[FakeResult(cred), FakeResult(cred)]),
        token_service=token_svc,
        revocation=revocation,
    )
    code = generate_totp_code(secret)

    tokens = await service.verificar_mfa_login(temp_token=temp_token, codigo=code)
    assert tokens.access_token is not None

    with pytest.raises(TokenRevogadoError):
        await service.verificar_mfa_login(temp_token=temp_token, codigo=code)


@pytest.mark.asyncio
async def test_mfa_setup_e_activate_mfa_pending_guard() -> None:
    """mfa_pending permite setup/activate no 1º acesso, mas bloqueia quando já ativo."""
    cred_novo = _make_credencial(
        papel="MEDICO",
        mfa_secret=None,
        mfa_ativo=False,
    )
    service_novo = _make_auth_service(
        FakeAsyncSession(results=[FakeResult(cred_novo), FakeResult(cred_novo)])
    )
    setup_dto = await service_novo.gerar_mfa_secret(
        cred_novo.usuario_id, from_mfa_pending=True
    )
    assert setup_dto.secret == cred_novo.mfa_secret
    ativado = await service_novo.ativar_mfa(
        cred_novo.usuario_id,
        generate_totp_code(setup_dto.secret),
        from_mfa_pending=True,
    )
    assert ativado is True
    assert cred_novo.mfa_ativo is True

    cred_ativo = _make_credencial(
        papel="MEDICO",
        mfa_secret=generate_totp_secret(),
        mfa_ativo=True,
    )
    service_ativo = _make_auth_service(
        FakeAsyncSession(results=[FakeResult(cred_ativo), FakeResult(cred_ativo)])
    )
    with pytest.raises(ForbiddenError, match="MFA já está ativo"):
        await service_ativo.gerar_mfa_secret(
            cred_ativo.usuario_id, from_mfa_pending=True
        )
    with pytest.raises(ForbiddenError, match="MFA já está ativo"):
        await service_ativo.ativar_mfa(
            cred_ativo.usuario_id, "123456", from_mfa_pending=True
        )


@pytest.mark.asyncio
async def test_mfa_setup_or_access_user_dependency_aceita_mfa_pending_e_access() -> (
    None
):
    """MfaSetupOrAccessUserDep aceita access/mfa_pending e rejeita revogados."""
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    user_id = uuid7()
    mfa_pending = token_svc.gerar_mfa_token(usuario_id=user_id, papel="MEDICO")
    access_pair = token_svc.gerar_tokens(usuario_id=user_id, papel="MEDICO")
    revocation = MemoryTokenRevocation()
    auth_settings = BearerAuthSettings(
        secret_key=TEST_JWT_SECRET,
        jwt_secret=TEST_JWT_SECRET,
        jwt_algorithm="HS256",
    )

    with pytest.raises(UnauthorizedError, match="Tipo de token"):
        await get_current_user(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=mfa_pending
            ),
            revocation=revocation,
            auth_settings=auth_settings,
        )

    pending_user = await get_mfa_setup_or_access_user(
        credentials=HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=mfa_pending
        ),
        revocation=revocation,
        auth_settings=auth_settings,
    )
    assert pending_user.usuario_id == user_id
    assert pending_user.token_type == "mfa_pending"

    access_user = await get_mfa_setup_or_access_user(
        credentials=HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=access_pair.access_token
        ),
        revocation=revocation,
        auth_settings=auth_settings,
    )
    assert access_user.token_type == "access"

    await revocation.revogar(str(pending_user.token_id))
    with pytest.raises(TokenRevogadoError):
        await get_mfa_setup_or_access_user(
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=mfa_pending
            ),
            revocation=revocation,
            auth_settings=auth_settings,
        )


@pytest.mark.asyncio
async def test_rotacionar_refresh_token_concorrencia_set_nx_apenas_um_sucesso() -> None:
    """Corrida simultânea em /refresh com mesmo refresh_token permite só 1 troca."""
    cred = _make_credencial(papel="ATENDENTE", mfa_ativo=False)
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    pair = token_svc.gerar_tokens(usuario_id=cred.usuario_id, papel="ATENDENTE")
    revocation = MemoryTokenRevocation()
    session = FakeAsyncSession(results=[FakeResult(cred), FakeResult(cred)])
    service = _make_auth_service(
        session, token_service=token_svc, revocation=revocation
    )

    outcomes = await asyncio.gather(
        service.rotacionar_refresh_token(pair.refresh_token),
        service.rotacionar_refresh_token(pair.refresh_token),
        return_exceptions=True,
    )
    sucessos = [o for o in outcomes if not isinstance(o, BaseException)]
    falhas = [o for o in outcomes if isinstance(o, TokenRevogadoError)]
    assert len(sucessos) == 1
    assert len(falhas) == 1


@pytest.mark.asyncio
async def test_revogar_sessao_revoga_access_token_mesmo_sem_refresh_token() -> None:
    """Logout apenas com Authorization Bearer deve revogar JTI do access_token."""
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    pair = token_svc.gerar_tokens(usuario_id=uuid7(), papel="MEDICO")
    revocation = MemoryTokenRevocation()
    service = _make_auth_service(
        FakeAsyncSession(), token_service=token_svc, revocation=revocation
    )

    await service.revogar_sessao(None, access_token=pair.access_token)
    acc_payload = token_svc.validar_access_token(pair.access_token)
    assert await revocation.is_revogado(acc_payload.jti) is True


@pytest.mark.asyncio
async def test_autenticar_rejeita_papel_paciente_com_dummy_verify() -> None:
    """Contas PACIENTE não podem autenticar via /auth/login corporativo."""
    cred = _make_credencial(
        identificador="paciente@example.com",
        senha_pura="SenhaPaciente123",
        papel=Role.PACIENTE.value,
    )
    session = FakeAsyncSession(results=[FakeResult(cred)])
    hasher = FakePasswordHasher()
    service = _make_auth_service(session, hasher=hasher)

    cmd = LoginCommand(
        identificador="paciente@example.com",
        senha="SenhaPaciente123",
        client_ip="127.0.0.1",
    )
    with pytest.raises(CredenciaisInvalidasError):
        await service.autenticar(cmd)

    assert hasher.dummy_calls == 1
    assert session.commits == 0


@pytest.mark.asyncio
async def test_rotacionar_refresh_token_rejeita_papel_paciente() -> None:
    """Refresh tokens associados a contas PACIENTE não podem ser rotacionados."""
    cred = _make_credencial(
        identificador="paciente@example.com",
        senha_pura="SenhaPaciente123",
        papel=Role.PACIENTE.value,
    )
    token_svc = JWTTokenService(secret_key=TEST_JWT_SECRET)
    pair = token_svc.gerar_tokens(
        usuario_id=cred.usuario_id,
        papel=Role.PACIENTE.value,
    )
    revocation = MemoryTokenRevocation()
    session = FakeAsyncSession(results=[FakeResult(cred)])
    service = _make_auth_service(
        session, token_service=token_svc, revocation=revocation
    )

    with pytest.raises(CredenciaisInvalidasError):
        await service.rotacionar_refresh_token(pair.refresh_token)

    payload = token_svc.validar_refresh_token(pair.refresh_token)
    assert await revocation.is_revogado(payload.jti) is True
