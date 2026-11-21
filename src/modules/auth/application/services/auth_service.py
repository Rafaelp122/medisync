"""Application service orchestrating authentication, Argon2id, lockout, MFA & JWT."""

import asyncio
import contextlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authz.revocation import TokenRevocationPort
from src.core.authz.roles import ROLES_REQUIRING_MFA, Role
from src.core.errors import ForbiddenError, NotFoundError
from src.modules.auth.application.dtos import (
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
from src.modules.auth.application.ports.token_service_port import TokenServicePort
from src.modules.auth.domain.exceptions import (
    ContaBloqueadaError,
    ContaDesativadaError,
    CredenciaisInvalidasError,
    MfaCodigoInvalidoError,
    TokenRevogadoError,
)
from src.modules.auth.domain.models.usuario_credencial import UsuarioCredencial
from src.modules.auth.domain.totp import (
    build_totp_uri,
    generate_totp_secret,
    verify_totp_code,
)


class AuthService:
    """Orquestra autenticação corporativa e proteção contra brute force.

    Regras: RN-AUT-01, RN-AUT-02, RN-AUT-05, RN-AUT-06, ADR-007, ADR-013, RF-01.
    Documentação: docs/explanation/domains/auth-domain.md
    """

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

    async def autenticar(self, command: LoginCommand) -> TokenPairDTO:
        """Autentica com rate limiting anti-brute force e checagem constant-time.

        Regras: RN-AUT-01, RN-AUT-02 (docs/explanation/domains/auth-domain.md),
        ADR-013, RF-01.
        Raises: ContaBloqueadaError, CredenciaisInvalidasError.
        """
        clean_ident = command.identificador.strip().lower()
        ip_key = f"ip:{command.client_ip}"
        account_key = f"acc:{clean_ident}"

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

        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.identificador == clean_ident,
        )
        cred = (await self._session.execute(stmt)).scalar_one_or_none()

        if cred is None or cred.papel == Role.PACIENTE.value:
            await asyncio.to_thread(self._hasher.dummy_verify)
            raise CredenciaisInvalidasError()

        if not cred.ativo:
            await asyncio.to_thread(self._hasher.dummy_verify)
            raise ContaDesativadaError()

        if cred.is_bloqueado():
            raise ContaBloqueadaError()

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

        cred.registrar_sucesso_login()
        await self._rate_limiter.resetar(ip_key)
        await self._rate_limiter.resetar(account_key)

        if self._hasher.needs_rehash(cred.senha_hash):
            novo_hash = await asyncio.to_thread(self._hasher.hash, command.senha)
            cred.atualizar_senha(novo_hash)

        await self._session.commit()

        if cred.papel in ROLES_REQUIRING_MFA:
            temp_token = self._token_service.gerar_mfa_token(
                usuario_id=cred.usuario_id,
                papel=cred.papel,
            )
            return TokenPairDTO(
                access_token=temp_token,
                refresh_token="",
                token_type="bearer",  # noqa: S106
                expires_in=300,
                refresh_expires_in=0,
                mfa_requerido=True,
                mfa_setup_requerido=not cred.mfa_ativo,
            )

        return self._token_service.gerar_tokens(
            usuario_id=cred.usuario_id,
            papel=cred.papel,
        )

    async def gerar_mfa_secret(
        self,
        usuario_id: UUID,
        *,
        from_mfa_pending: bool = False,
    ) -> MfaSetupDTO:
        """Gera chave secreta Base32 e URI para app autenticador (TOTP).

        Impede sobrescrita via token temporário mfa_pending se MFA já estiver ativo.
        Regras: ADR-007 (MFA), RF-01 e docs/explanation/domains/auth-domain.md.
        """
        cred = await self.obter_usuario_por_id(usuario_id)
        if cred is None:
            raise NotFoundError(
                f"Usuário '{usuario_id}' não encontrado para configuração de MFA."
            )
        if from_mfa_pending and cred.mfa_ativo:
            raise ForbiddenError(
                f"MFA já está ativo para o usuário '{usuario_id}'; "
                "use /auth/mfa/verify ou token de acesso completo."
            )

        secret = generate_totp_secret()
        uri = build_totp_uri(secret, cred.identificador, issuer="MediSync")
        cred.mfa_secret = secret
        await self._session.commit()
        return MfaSetupDTO(secret=secret, uri=uri)

    async def ativar_mfa(
        self,
        usuario_id: UUID,
        codigo: str = "",
        *,
        from_mfa_pending: bool = False,
    ) -> bool:
        """Valida o primeiro código TOTP de 6 dígitos e ativa o MFA para a conta.

        Impede re-ativação via token mfa_pending se MFA já estiver ativo.
        Regras: ADR-007, RF-01 e docs/explanation/domains/auth-domain.md.
        """
        cred = await self.obter_usuario_por_id(usuario_id)
        if cred is None:
            raise NotFoundError(
                f"Usuário '{usuario_id}' não encontrado para ativação de MFA."
            )
        if from_mfa_pending and cred.mfa_ativo:
            raise ForbiddenError(
                f"MFA já está ativo para o usuário '{usuario_id}'; "
                "utilize /auth/mfa/verify para concluir o segundo fator."
            )
        if not cred.mfa_secret:
            raise MfaCodigoInvalidoError(
                f"Segredo MFA não configurado para o usuário '{usuario_id}'; "
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
        """Valida TOTP contra token temporário de uso único e emite tokens definitivos.

        Regras: ADR-007, RF-01 e docs/explanation/domains/auth-domain.md.
        """
        payload = self._token_service.validar_mfa_token(temp_token)
        if await self._revocation.is_revogado(payload.jti):
            raise TokenRevogadoError(
                f"O token temporário MFA (jti={payload.jti}) "
                "já foi utilizado ou revogado."
            )

        cred = await self.obter_usuario_por_id(payload.sub)
        if (
            cred is None
            or not cred.ativo
            or cred.is_bloqueado()
            or not cred.mfa_secret
            or not cred.mfa_ativo
        ):
            raise CredenciaisInvalidasError(
                f"Sessão temporária para usuário '{payload.sub}' ou credencial "
                "indisponível ou com MFA inativo para segundo fator."
            )

        if not verify_totp_code(cred.mfa_secret, codigo):
            raise MfaCodigoInvalidoError(
                f"Código TOTP '{codigo}' fornecido para o usuário '{payload.sub}' "
                "é inválido ou expirou; esperado código numérico de 6 dígitos válido."
            )

        remaining_seconds = max(
            1, int((payload.exp - datetime.now(UTC)).total_seconds())
        )
        marcado = await self._revocation.marcar_revogado_se_nao_revogado(
            payload.jti,
            exp_segundos=remaining_seconds,
        )
        if not marcado:
            raise TokenRevogadoError(
                f"O token temporário MFA (jti={payload.jti}) já foi consumido."
            )

        return self._token_service.gerar_tokens(
            usuario_id=cred.usuario_id,
            papel=cred.papel,
        )

    async def rotacionar_refresh_token(self, refresh_token: str) -> TokenPairDTO:
        """Rotaciona refresh token de uso único com revogação atômica SET NX.

        Regras: RN-AUT-05 (docs/explanation/domains/auth-domain.md), ADR-013, RF-01.
        Raises: TokenRevogadoError, CredenciaisInvalidasError.
        """
        payload: TokenPayloadDTO = self._token_service.validar_refresh_token(
            refresh_token
        )

        remaining_seconds = max(
            1, int((payload.exp - datetime.now(UTC)).total_seconds())
        )
        marcado = await self._revocation.marcar_revogado_se_nao_revogado(
            payload.jti,
            exp_segundos=remaining_seconds,
        )
        if not marcado:
            raise TokenRevogadoError(
                f"O token de atualização (jti={payload.jti}) apresentado já foi "
                "utilizado ou revogado."
            )

        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.usuario_id == payload.sub,
        )
        cred = (await self._session.execute(stmt)).scalar_one_or_none()

        if (
            cred is None
            or cred.papel == Role.PACIENTE.value
            or payload.papel == Role.PACIENTE.value
            or not cred.ativo
            or cred.is_bloqueado()
        ):
            raise CredenciaisInvalidasError(
                f"Sessão expirada ou conta indisponível para usuário '{payload.sub}'."
            )

        return self._token_service.gerar_tokens(
            usuario_id=cred.usuario_id,
            papel=cred.papel,
        )

    async def validar_access_token(self, token: str) -> TokenPayloadDTO:
        """Valida assinatura do access token JWT e consulta blacklist de revogação.

        Regras: RN-AUT-05 (docs/explanation/domains/auth-domain.md), ADR-013, RF-01.
        Raises: TokenRevogadoError, TokenInvalidoError.
        """
        payload = self._token_service.validar_access_token(token)
        if await self._revocation.is_revogado(payload.jti):
            raise TokenRevogadoError(
                f"O token de acesso (jti={payload.jti}) apresentado foi revogado."
            )
        return payload

    async def revogar_sessao(
        self,
        refresh_token: str | None = None,
        access_token: str | None = None,
    ) -> None:
        """Revoga tokens de refresh e access na blacklist distribuída Valkey.

        Regras: RN-AUT-06 (docs/explanation/domains/auth-domain.md), ADR-013, RF-01.
        """
        now = datetime.now(UTC)
        if refresh_token:
            with contextlib.suppress(Exception):
                payload = self._token_service.validar_refresh_token(refresh_token)
                remaining_seconds = max(1, int((payload.exp - now).total_seconds()))
                await self._revocation.revogar(
                    payload.jti, exp_segundos=remaining_seconds
                )

        if access_token:
            with contextlib.suppress(Exception):
                acc_payload = self._token_service.validar_access_token(access_token)
                acc_remaining = max(1, int((acc_payload.exp - now).total_seconds()))
                await self._revocation.revogar(
                    acc_payload.jti, exp_segundos=acc_remaining
                )

    async def obter_usuario_por_id(self, usuario_id: UUID) -> UsuarioCredencial | None:
        """Recupera entidade de credenciais do usuário autenticado na plataforma.

        Regras: RN-AUT-01 (docs/explanation/domains/auth-domain.md), ADR-013, RF-01.
        """
        stmt = select(UsuarioCredencial).where(
            UsuarioCredencial.usuario_id == usuario_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()
