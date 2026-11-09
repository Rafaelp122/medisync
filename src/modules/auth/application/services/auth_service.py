"""Application service orchestrating authentication, lockout, and sessions."""

import asyncio
import contextlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authz.roles import ROLES_REQUIRING_MFA
from src.core.errors import ConflictError, MfaCodigoInvalidoError, NotFoundError
from src.modules.auth.application.dtos import (
    CadastrarCredencialCommand,
    LoginCommand,
    MfaSetupDTO,
    TokenPairDTO,
    TokenPayloadDTO,
)
from src.modules.auth.application.ports.auth_rate_limiter_port import (
    AuthRateLimiterPort,
)
from src.modules.auth.application.ports.password_hasher_port import (
    PasswordHasherPort,
)
from src.modules.auth.application.ports.token_revocation_port import (
    TokenRevocationPort,
)
from src.modules.auth.application.ports.token_service_port import (
    TokenServicePort,
)
from src.modules.auth.domain.exceptions import (
    ContaBloqueadaError,
    ContaDesativadaError,
    CredenciaisInvalidasError,
    TokenRevogadoError,
)
from src.modules.auth.domain.models import UsuarioCredencial
from src.modules.auth.domain.totp import (
    build_totp_uri,
    generate_totp_secret,
    verify_totp_code,
)


class AuthService:
    """Authentication and session lifecycle application service (OWASP compliant)."""

    def __init__(
        self,
        session: AsyncSession,
        hasher: PasswordHasherPort,
        token_service: TokenServicePort,
        rate_limiter: AuthRateLimiterPort,
        revocation: TokenRevocationPort,
        max_attempts: int = 5,
        window_seconds: int = 900,
    ) -> None:
        self._session = session
        self._hasher = hasher
        self._token_service = token_service
        self._rate_limiter = rate_limiter
        self._revocation = revocation

        self._max_attempts = max_attempts
        self._window_seconds = window_seconds

    async def cadastrar_credencial(
        self, command: CadastrarCredencialCommand
    ) -> UsuarioCredencial:
        """Provisiona credenciais com hash seguro Argon2id e identificador canônico.

        Regras: RN-AUT-01 (auth-domain.md), ADR-007, RF-01.
        Raises: ConflictError.
        """
        clean_ident = command.identificador.strip().lower()
        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.organizacao_id == command.organizacao_id,
            UsuarioCredencial.identificador == clean_ident,
        )
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing is not None:
            raise ConflictError(
                f"Identificador '{clean_ident}' já cadastrado na organização."
            )

        senha_hash = self._hasher.hash(command.senha_pura)
        cred = UsuarioCredencial(
            organizacao_id=command.organizacao_id,
            usuario_id=command.usuario_id,
            identificador=clean_ident,
            senha_hash=senha_hash,
            papel=command.papel,
        )
        self._session.add(cred)
        await self._session.flush()
        return cred

    async def autenticar(self, command: LoginCommand) -> TokenPairDTO:
        """Autentica com rate limiting anti-brute force e checagem constant-time.

        Regras: RN-AUT-02, RN-AUT-03, RN-AUT-04 (auth-domain.md), ADR-007, RF-01.
        Raises: ContaBloqueadaError, CredenciaisInvalidasError.
        """
        clean_ident = command.identificador.strip().lower()
        ip_key = f"ip:{command.client_ip}"
        account_key = f"acc:{command.organizacao_id}:{clean_ident}"

        # 1. Rate limiter check (anti-brute force / credential stuffing)
        ip_check = await self._rate_limiter.verificar_e_incrementar(
            chave=ip_key,
            limite=self._max_attempts * 3,
            janela_segundos=self._window_seconds,
        )
        if not ip_check.permitido:
            raise ContaBloqueadaError(
                "Muitas tentativas a partir deste endereço IP. "
                f"Tente novamente em {ip_check.retry_after_segundos} segundos."
            )

        acc_check = await self._rate_limiter.verificar_e_incrementar(
            chave=account_key,
            limite=self._max_attempts,
            janela_segundos=self._window_seconds,
        )
        if not acc_check.permitido:
            raise ContaBloqueadaError(
                "Conta temporariamente bloqueada por excesso de tentativas falhas. "
                f"Tente novamente em {acc_check.retry_after_segundos} segundos."
            )

        # 2. Database lookup
        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.organizacao_id == command.organizacao_id,
            UsuarioCredencial.identificador == clean_ident,
        )
        res = await self._session.execute(stmt)
        cred = res.scalar_one_or_none()

        # 3. User enumeration mitigation: constant-time dummy verify if absent
        if cred is None:
            await asyncio.to_thread(self._hasher.dummy_verify)
            raise CredenciaisInvalidasError()

        # 4. Check account active and locked status
        if not cred.ativo:
            await asyncio.to_thread(self._hasher.dummy_verify)
            raise ContaDesativadaError()

        if cred.is_bloqueado():
            raise ContaBloqueadaError()

        # 5. Argon2id password verification
        is_valida = await asyncio.to_thread(
            self._hasher.verify, command.senha, cred.senha_hash
        )
        if not is_valida:
            recem_bloqueado = cred.registrar_falha_login(
                max_falhas=self._max_attempts,
                minutos_bloqueio=self._window_seconds // 60,
            )
            await self._session.commit()
            if recem_bloqueado:
                raise ContaBloqueadaError()
            raise CredenciaisInvalidasError()

        # 6. Success: reset counters and lockout
        cred.registrar_sucesso_login()
        await self._rate_limiter.resetar(ip_key)
        await self._rate_limiter.resetar(account_key)

        # 7. Check if hash upgrade is required
        if self._hasher.needs_rehash(cred.senha_hash):
            novo_hash = self._hasher.hash(command.senha)
            cred.atualizar_senha(novo_hash)

        await self._session.commit()

        # 8. Check if MFA is required (roles in ROLES_REQUIRING_MFA)
        if cred.papel in ROLES_REQUIRING_MFA:
            temp_token = self._token_service.gerar_mfa_token(
                usuario_id=cred.usuario_id,
                organizacao_id=cred.organizacao_id,
                papel=cred.papel,
            )
            if cred.mfa_ativo:
                return TokenPairDTO(
                    access_token=temp_token,
                    refresh_token="",
                    token_type="bearer",  # noqa: S106
                    expires_in=300,
                    refresh_expires_in=0,
                    mfa_requerido=True,
                    mfa_setup_requerido=False,
                )
            return TokenPairDTO(
                access_token=temp_token,
                refresh_token="",
                token_type="bearer",  # noqa: S106
                expires_in=300,
                refresh_expires_in=0,
                mfa_requerido=True,
                mfa_setup_requerido=True,
            )

        # 9. Issue JWT token pair
        return self._token_service.gerar_tokens(
            usuario_id=cred.usuario_id,
            organizacao_id=cred.organizacao_id,
            papel=cred.papel,
        )

    async def gerar_mfa_secret(
        self, usuario_id: UUID, organizacao_id: int | None = None
    ) -> MfaSetupDTO:
        """Gera chave secreta Base32 e URI para app autenticador (TOTP).

        Regras: ADR-007 (MFA), RF-01 e docs/explanation/domains/auth-domain.md.
        """
        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.usuario_id == usuario_id
        )
        if organizacao_id is not None:
            stmt = stmt.where(UsuarioCredencial.organizacao_id == organizacao_id)
        res = await self._session.execute(stmt)
        cred = res.scalar_one_or_none()
        if cred is None:
            raise NotFoundError(
                f"Usuário '{usuario_id}' não encontrado para configuração de MFA."
            )

        secret = generate_totp_secret()
        uri = build_totp_uri(secret, cred.identificador, issuer="MediSync")
        cred.mfa_secret = secret
        await self._session.commit()
        return MfaSetupDTO(secret=secret, uri=uri)

    async def ativar_mfa(
        self, usuario_id: UUID, organizacao_id: int | None = None, codigo: str = ""
    ) -> bool:
        """Valida o primeiro código TOTP de 6 dígitos e ativa o MFA para a conta.

        Regras: ADR-007, RF-01 e docs/explanation/domains/auth-domain.md.
        """
        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.usuario_id == usuario_id
        )
        if organizacao_id is not None:
            stmt = stmt.where(UsuarioCredencial.organizacao_id == organizacao_id)
        res = await self._session.execute(stmt)
        cred = res.scalar_one_or_none()
        if cred is None:
            raise NotFoundError(
                f"Usuário '{usuario_id}' não encontrado para ativação de MFA."
            )

        if not cred.mfa_secret:
            raise MfaCodigoInvalidoError(
                f"Usuário '{usuario_id}' não possui segredo MFA gerado; "
                "execute o setup prévio."
            )

        is_valido = verify_totp_code(cred.mfa_secret, codigo)
        if not is_valido:
            raise MfaCodigoInvalidoError(
                f"Código TOTP '{codigo}' inválido para ativação de MFA; "
                "esperado token numérico de 6 dígitos válido."
            )

        cred.mfa_ativo = True
        await self._session.commit()
        return True

    async def verificar_mfa_login(self, temp_token: str, codigo: str) -> TokenPairDTO:
        """Valida TOTP contra token temporário e emite tokens definitivos.

        Regras: ADR-007, RF-01 e docs/explanation/domains/auth-domain.md.
        """
        payload = self._token_service.validar_mfa_token(temp_token)
        cred = await self.obter_usuario_por_id(payload.sub, payload.org_id)
        if cred is None or not cred.ativo or cred.is_bloqueado() or not cred.mfa_secret:
            raise CredenciaisInvalidasError(
                f"Sessão temporária para usuário '{payload.sub}' ou credencial "
                "indisponível para segundo fator."
            )

        is_valido = verify_totp_code(cred.mfa_secret, codigo)
        if not is_valido:
            raise MfaCodigoInvalidoError(
                f"Código TOTP '{codigo}' fornecido para o usuário '{payload.sub}' "
                "é inválido ou expirou; esperado código numérico de 6 dígitos válido."
            )

        return self._token_service.gerar_tokens(
            usuario_id=cred.usuario_id,
            organizacao_id=cred.organizacao_id,
            papel=cred.papel,
        )

    async def rotacionar_refresh_token(self, refresh_token: str) -> TokenPairDTO:
        """Rotaciona refresh token de uso único com revogação distribuída imediata.

        Regras: RN-AUT-05 (auth-domain.md), ADR-007, RF-01.
        Raises: TokenRevogadoError, CredenciaisInvalidasError.
        """
        payload: TokenPayloadDTO = self._token_service.validar_refresh_token(
            refresh_token
        )

        # Check revocation
        if await self._revocation.is_revogado(payload.jti):
            raise TokenRevogadoError(
                "O token de atualização apresentado já foi utilizado ou revogado."
            )

        # Mark old token as revoked (one-time use rotation) with dynamic remaining TTL
        now = datetime.now(UTC)
        remaining_seconds = max(1, int((payload.exp - now).total_seconds()))
        await self._revocation.revogar(payload.jti, exp_segundos=remaining_seconds)

        # Validate user account is still valid and active in database
        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.organizacao_id == payload.org_id,
            UsuarioCredencial.usuario_id == payload.sub,
        )
        res = await self._session.execute(stmt)
        cred = res.scalar_one_or_none()

        if cred is None or not cred.ativo or cred.is_bloqueado():
            raise CredenciaisInvalidasError(
                "Sessão expirada ou conta indisponível para renovação."
            )

        return self._token_service.gerar_tokens(
            usuario_id=cred.usuario_id,
            organizacao_id=cred.organizacao_id,
            papel=cred.papel,
        )

    async def validar_access_token(self, token: str) -> TokenPayloadDTO:
        """Valida assinatura do access token JWT e consulta blacklist de revogação.

        Regras: RN-AUT-05 (auth-domain.md), ADR-007, RF-01.
        Raises: TokenRevogadoError, TokenInvalidoError.
        """
        payload = self._token_service.validar_access_token(token)
        if await self._revocation.is_revogado(payload.jti):
            raise TokenRevogadoError("O token de acesso apresentado foi revogado.")
        return payload

    async def revogar_sessao(
        self, refresh_token: str, access_token: str | None = None
    ) -> None:
        """Revoga tokens de refresh e access na blacklist distribuída Valkey.

        Regras: RN-AUT-05 (auth-domain.md), ADR-007, RF-01.
        """
        now = datetime.now(UTC)
        with contextlib.suppress(Exception):
            payload = self._token_service.validar_refresh_token(refresh_token)
            remaining_seconds = max(1, int((payload.exp - now).total_seconds()))
            await self._revocation.revogar(payload.jti, exp_segundos=remaining_seconds)

        if access_token:
            with contextlib.suppress(Exception):
                acc_payload = self._token_service.validar_access_token(access_token)
                acc_remaining = max(1, int((acc_payload.exp - now).total_seconds()))
                await self._revocation.revogar(
                    acc_payload.jti, exp_segundos=acc_remaining
                )

    async def obter_usuario_por_id(
        self, usuario_id: UUID, organizacao_id: int
    ) -> UsuarioCredencial | None:
        """Recupera entidade de credenciais respeitando o isolamento multi-tenant.

        Regras: RN-AUT-01 (auth-domain.md), ADR-001, RF-01.
        """
        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.organizacao_id == organizacao_id,
            UsuarioCredencial.usuario_id == usuario_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()
