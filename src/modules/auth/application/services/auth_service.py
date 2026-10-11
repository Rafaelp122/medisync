"""Application service orchestrating authentication, lockout, and sessions."""

import contextlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.errors import ConflictError
from src.modules.auth.application.dtos import (
    CadastrarCredencialCommand,
    LoginCommand,
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


class _LocalMemoryRevocation:
    """In-memory revocation store used as zero-dependency fallback."""

    def __init__(self) -> None:
        self._revoked: set[str] = set()

    async def revogar(self, jti: str, exp_segundos: int = 86400 * 7) -> None:
        self._revoked.add(jti)

    async def is_revogado(self, jti: str) -> bool:
        return jti in self._revoked


class AuthService:
    """Authentication and session lifecycle application service (OWASP compliant)."""

    def __init__(
        self,
        session: AsyncSession,
        hasher: PasswordHasherPort,
        token_service: TokenServicePort,
        rate_limiter: AuthRateLimiterPort,
        revocation: TokenRevocationPort | None = None,
    ) -> None:
        self._session = session
        settings = get_settings()
        self._hasher = hasher
        self._token_service = token_service
        self._rate_limiter = rate_limiter
        self._revocation: TokenRevocationPort = revocation or _LocalMemoryRevocation()

        self._max_attempts = settings.AUTH_RATE_LIMIT_MAX_ATTEMPTS
        self._window_seconds = settings.AUTH_RATE_LIMIT_WINDOW_SECONDS

    async def cadastrar_credencial(
        self, command: CadastrarCredencialCommand
    ) -> UsuarioCredencial:
        """Register or provision initial credentials for an authorized staff member."""
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
        """Authenticate user credentials with rate limiting and constant-time check."""
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
            self._hasher.dummy_verify()
            raise CredenciaisInvalidasError()

        # 4. Check account active and locked status
        if not cred.ativo:
            self._hasher.dummy_verify()
            raise ContaDesativadaError()

        if cred.is_bloqueado():
            raise ContaBloqueadaError()

        # 5. Argon2id password verification
        is_valida = self._hasher.verify(command.senha, cred.senha_hash)
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

        # 8. Issue JWT token pair
        return self._token_service.gerar_tokens(
            usuario_id=cred.usuario_id,
            organizacao_id=cred.organizacao_id,
            papel=cred.papel,
        )

    async def rotacionar_refresh_token(self, refresh_token: str) -> TokenPairDTO:
        """Rotate refresh token: invalidate presented token and issue a fresh pair."""
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
        """Validate access token via configured token service and check revocation."""
        payload = self._token_service.validar_access_token(token)
        if await self._revocation.is_revogado(payload.jti):
            raise TokenRevogadoError("O token de acesso apresentado foi revogado.")
        return payload

    async def revogar_sessao(
        self, refresh_token: str, access_token: str | None = None
    ) -> None:
        """Revoke a refresh token (and optionally access token) on user logout."""
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
        """Retrieve user credentials entity by identity ID and tenant."""
        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.organizacao_id == organizacao_id,
            UsuarioCredencial.usuario_id == usuario_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()
