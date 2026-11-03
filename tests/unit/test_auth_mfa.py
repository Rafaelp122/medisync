"""Unit tests for Tripartite Authentication and TOTP MFA (RFC 6238).

Regras: ADR-007, RF-01, CFM nº 2.454/2026, CFM nº 2.314/2022.
"""

from datetime import date
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest
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
    IdentityReaderPort,
    PacienteAuthLookupData,
    PacienteAuthLookupDTO,
)
from src.modules.auth.application.ports.password_hasher_port import (
    PasswordHasherPort,
)
from src.modules.auth.application.services.auth_service import AuthService
from src.modules.auth.application.services.patient_auth_service import (
    PatientAuthService,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.auth.domain.exceptions import (
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

from tests.doubles import FakeAsyncSession, FakeResult


class FakePasswordHasher(PasswordHasherPort):
    """Named fake implementation of PasswordHasherPort."""

    def hash(self, password: str) -> str:
        return f"hashed_{password}"

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return hashed_password == f"hashed_{plain_password}"

    def needs_rehash(self, hashed_password: str) -> bool:
        return False

    def dummy_verify(self) -> None:
        pass


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


class FakeIdentityReader(IdentityReaderPort):
    """Named fake implementation of IdentityReaderPort."""

    def __init__(self, paciente: PacienteAuthLookupDTO | None = None) -> None:
        self.paciente = paciente

    async def buscar_paciente_por_telefone(
        self,
        organizacao_id: int,
        telefone: str,
        cpf: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        return self.paciente

    async def buscar_paciente_cadsus(
        self,
        organizacao_id: int,
        cpf: str | None = None,
        data_nascimento: date | None = None,
        cns: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        return self.paciente


TEST_JWT_SECRET = "super-secret-key-for-testing-purposes-123456"


def _make_credencial(
    usuario_id: UUID | None = None,
    organizacao_id: int = 1,
    identificador: str = "dr.silva@medisync.com",
    senha_pura: str = "senha123",
    papel: str = "MEDICO",
    mfa_secret: str | None = None,
    mfa_ativo: bool = False,
) -> UsuarioCredencial:
    return UsuarioCredencial(
        organizacao_id=organizacao_id,
        usuario_id=usuario_id or uuid7(),
        identificador=identificador,
        senha_hash=f"hashed_{senha_pura}",
        papel=papel,
        mfa_secret=mfa_secret,
        mfa_ativo=mfa_ativo,
    )


def _make_auth_service(
    session: FakeAsyncSession,
    token_service: JWTTokenService | None = None,
) -> AuthService:
    return AuthService(
        session=cast("AsyncSession", session),
        hasher=FakePasswordHasher(),
        token_service=token_service or JWTTokenService(secret_key=TEST_JWT_SECRET),
        rate_limiter=FakeAuthRateLimiter(),
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

    setup_dto = await service.gerar_mfa_secret(
        usuario_id=cred.usuario_id, organizacao_id=cred.organizacao_id
    )

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
        await service.gerar_mfa_secret(usuario_id=uid, organizacao_id=1)

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
            organizacao_id=cred.organizacao_id,
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
        organizacao_id=cred.organizacao_id,
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
        organizacao_id=cred.organizacao_id,
        client_ip="127.0.0.1",
    )
    tokens = await service.autenticar(cmd)

    assert tokens.mfa_requerido is True
    assert tokens.refresh_token == ""
    assert tokens.access_token is not None

    payload = token_svc.validar_mfa_token(tokens.access_token)
    assert payload.sub == cred.usuario_id
    assert payload.org_id == cred.organizacao_id
    assert payload.mfa_pending is True


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
        organizacao_id=cred.organizacao_id,
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
        organizacao_id=cred.organizacao_id,
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
        organizacao_id=1,
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
        organizacao_id=1,
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
            organizacao_id=1,
            cpf="11144477735",
            data_nascimento=date(1990, 5, 15),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "PACIENTE_NAO_ENCONTRADO"
