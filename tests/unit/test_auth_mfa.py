"""Unit tests for Tripartite Authentication and TOTP MFA (RFC 6238).

Regras: ADR-007, ADR-013, RF-01, CFM nº 2.454/2026, CFM nº 2.314/2022.
"""

from datetime import date
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest
from src.core.authz.roles import Role
from src.core.errors import MfaCodigoInvalidoError, NotFoundError
from src.core.uuid7 import uuid7
from src.modules.auth.application.dtos import (
    LoginCommand,
    RateLimitResultDTO,
)
from src.modules.auth.application.ports.auth_rate_limiter_port import (
    AuthRateLimiterPort,
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
    PacienteNaoEncontradoError,
)
from src.modules.auth.domain.models import UsuarioCredencial
from src.modules.auth.domain.totp import (
    build_totp_uri,
    generate_totp_code,
    generate_totp_secret,
    verify_totp_code,
)
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.auth.infrastructure.valkey_token_revocation import (
    MemoryTokenRevocation,
)

from tests.doubles import (
    FakeAsyncSession,
    FakeIdentityReader,
    FakePasswordHasher,
    FakeResult,
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
) -> AuthService:
    return AuthService(
        session=cast("AsyncSession", session),
        hasher=hasher or FakePasswordHasher(),
        token_service=token_service or JWTTokenService(secret_key=TEST_JWT_SECRET),
        rate_limiter=FakeAuthRateLimiter(),
        revocation=revocation or MemoryTokenRevocation(),
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
    """Autenticação sem senha CADSUS/Gov.br desambigua por CPF/CNS e emite token."""
    paciente_id = uuid7()
    lookup_paciente = PacienteAuthLookupData(
        id=paciente_id,
        telefone="11987654321",
        cpf="11144477735",
        nome_completo="Carlos Paciente",
    )
    fake_reader = FakeIdentityReader(paciente=lookup_paciente)
    service = PatientAuthService(
        identity_reader=fake_reader,
        secret_key=TEST_JWT_SECRET,
    )

    resultado = await service.autenticar_cadsus_govbr(
        cpf="11144477735",
        data_nascimento=date(1990, 5, 15),
    )

    assert resultado.paciente_id == paciente_id
    assert resultado.role == "PACIENTE"
    assert resultado.token_type == "bearer"
    assert resultado.access_token is not None


@pytest.mark.asyncio
async def test_autenticar_cadsus_govbr_paciente_nao_encontrado() -> None:
    """Falha de desambiguação CADSUS levanta PacienteNaoEncontradoError."""
    fake_reader = FakeIdentityReader(paciente=None)
    service = PatientAuthService(
        identity_reader=fake_reader,
        secret_key=TEST_JWT_SECRET,
    )

    with pytest.raises(PacienteNaoEncontradoError) as exc_info:
        await service.autenticar_cadsus_govbr(
            cpf="11144477735",
            data_nascimento=date(1990, 5, 15),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "PACIENTE_NAO_ENCONTRADO"


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
