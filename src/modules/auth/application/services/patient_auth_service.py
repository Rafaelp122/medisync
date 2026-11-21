"""Application service orchestrating passwordless patient OTP authentication."""

import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from datetime import date
from typing import Any, Literal
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authz.roles import Role
from src.core.authz.token import create_access_token
from src.core.errors import ConflictError, ValidationError
from src.core.privacy import mascarar_cns, mascarar_cpf
from src.core.uuid7 import uuid7
from src.modules.auth.application.dtos import (
    IdentificarPacienteCommand,
    IdentificarPacienteOutputDTO,
    LoginPacienteSenhaCommand,
    MetodosAutenticacaoPacienteOutputDTO,
    RegistrarPacienteCommand,
    RegistrarPacienteOutputDTO,
    SolicitarOtpInputDTO,
    SolicitarOtpOutputDTO,
    VerificarOtpInputDTO,
    VerificarOtpOutputDTO,
)
from src.modules.auth.application.ports.active_attendance_lookup_port import (
    ActiveAttendanceLookupPort,
)
from src.modules.auth.application.ports.auth_rate_limiter_port import (
    AuthRateLimiterPort,
)
from src.modules.auth.application.ports.identity_reader_port import (
    IdentityReaderPort,
    PacienteAuthLookupDTO,
)
from src.modules.auth.application.ports.identity_writer_port import (
    IdentityWriterPort,
)
from src.modules.auth.application.ports.password_hasher_port import (
    PasswordHasherPort,
)
from src.modules.auth.application.ports.patient_credential_repository_port import (
    PatientCredentialRepositoryPort,
)
from src.modules.auth.application.ports.sms_sender_port import (
    SmsSenderPort,
)
from src.modules.auth.domain.exceptions import (
    ContaBloqueadaError,
    ContaDesativadaError,
    CredenciaisInvalidasError,
    IdentificacaoRateLimitExcedidoError,
    OtpInvalidoOuExpiradoError,
    OtpRateLimitExcedidoError,
    OtpTentativasExcedidasError,
    PacienteNaoEncontradoError,
)
from src.modules.auth.domain.models.usuario_credencial import UsuarioCredencial
from src.modules.auth.domain.validators import validate_cpf, validate_telefone

logger = logging.getLogger("medisync.auth.patient_auth")

OTP_TTL_SECONDS = 300  # 5 minutes validity
OTP_RATE_LIMIT_WINDOW = 900  # 15 minutes window
OTP_MAX_REQUESTS_PER_WINDOW = 3
OTP_MAX_VERIFY_ATTEMPTS = 3
IDENTIFY_RATE_LIMIT_WINDOW = 900
IDENTIFY_MAX_REQUESTS_PER_IP = 15
IDENTIFY_MAX_REQUESTS_PER_IDENT = 10
REGISTER_RATE_LIMIT_WINDOW = 900
REGISTER_MAX_REQUESTS_PER_IP = 10
PASSWORD_MAX_FAILURES = 5
PASSWORD_LOCKOUT_MINUTES = 15
UNUSABLE_CREDENTIAL_MARKER = "!UNUSABLE:"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash_pii_key(value: str) -> str:
    """Hash PII identifier into a non-reversible 16-char Valkey key suffix."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _mascarar_telefone(clean_telefone: str) -> str:
    """Mask phone number for safe exception display without leaking PII."""
    if len(clean_telefone) >= 8:
        return f"{clean_telefone[:4]}****{clean_telefone[-4:]}"
    return "****"


class PatientAuthService:
    """Autenticação híbrida de pacientes (OTP SMS, CADSUS/Gov.br, senha Argon2id).

    Regras: RN-AUT-02, RN-AUT-03, RN-AUT-04, RN-AUT-09, ADR-012, ADR-013, RF-01.
    Documentação: docs/explanation/domains/auth-domain.md e
    docs/adrs/ADR-012-Transicao-100-SUS-Consorcios-Intermunicipais-e-Autenticacao-Tripartida.md
    """

    def __init__(
        self,
        identity_reader: IdentityReaderPort | None = None,
        valkey_client: Redis | None = None,
        sms_sender: SmsSenderPort | None = None,
        secret_key: str | None = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
        is_debug: bool = False,
        active_attendance_lookup: ActiveAttendanceLookupPort | None = None,
        identity_writer: IdentityWriterPort | None = None,
        credential_repo: PatientCredentialRepositoryPort | None = None,
        password_hasher: PasswordHasherPort | None = None,
        govbr_oidc_enabled: bool = False,
        session: AsyncSession | None = None,
        expose_debug_otp: bool = False,
        rate_limiter: AuthRateLimiterPort | None = None,
    ) -> None:
        self._identity_reader = identity_reader
        self._valkey = valkey_client
        self._sms_sender = sms_sender
        self._secret_key = (
            secret_key
            or "dev-insecure-jwt-secret-key-change-in-production-min-32-chars"
        )
        self._algorithm = algorithm
        self._access_token_expire_minutes = access_token_expire_minutes
        self._expose_debug_otp = expose_debug_otp or is_debug
        self._active_attendance = active_attendance_lookup
        self._identity_writer = identity_writer
        self._credential_repo = credential_repo
        self._password_hasher = password_hasher
        self._govbr_oidc_enabled = govbr_oidc_enabled
        self._session = session
        self._rate_limiter = rate_limiter
        # In-memory storage fallback for unit testing when Valkey is None
        self._memory_otp: dict[str, dict[str, Any]] = {}
        self._memory_ratelimit: dict[str, list[float]] = {}

    async def _resolve_active_attendance(self, paciente_id: UUID) -> UUID | None:
        if self._active_attendance is None:
            return None
        return await self._active_attendance.buscar_atendimento_ativo_paciente(
            paciente_id=paciente_id,
        )

    async def _calculate_valkey_retry_after(
        self, redis_key: str, now: float, window_seconds: int
    ) -> int:
        """Calculate seconds remaining until the oldest entry slides out of window."""
        if self._valkey is None:
            return window_seconds
        oldest_entries: list[Any] = await self._valkey.zrange(  # pyright: ignore[reportUnknownMemberType]
            redis_key, 0, 0, withscores=True
        )
        if not oldest_entries:
            return window_seconds
        oldest_time = float(oldest_entries[0][1])
        return max(1, int(oldest_time + window_seconds - now))

    async def _valkey_sliding_window(
        self,
        redis_key: str,
        max_requests: int,
        window_seconds: int,
        now: float,
    ) -> int | None:
        """Check Valkey sliding window; return None if unavailable or retry seconds."""
        if self._valkey is None:
            return None
        window_start = now - window_seconds
        try:
            async with self._valkey.pipeline(transaction=True) as pipe:
                await pipe.zremrangebyscore(redis_key, 0, window_start)  # pyright: ignore[reportUnknownMemberType]
                await pipe.zcard(redis_key)  # pyright: ignore[reportUnknownMemberType]
                results: list[Any] = await pipe.execute()  # pyright: ignore[reportUnknownMemberType]

            if int(results[1]) >= max_requests:
                return await self._calculate_valkey_retry_after(
                    redis_key, now, window_seconds
                )

            async with self._valkey.pipeline(transaction=True) as pipe:
                await pipe.zadd(redis_key, {str(uuid7()): now})  # pyright: ignore[reportUnknownMemberType]
                await pipe.expire(redis_key, window_seconds + 60)  # pyright: ignore[reportUnknownMemberType]
                await pipe.execute()  # pyright: ignore[reportUnknownMemberType]
            return 0
        except Exception as exc:
            logger.warning("Valkey rate limit failed, falling back to memory: %s", exc)
            return None

    def _memory_sliding_window(
        self,
        mem_key: str,
        max_requests: int,
        window_seconds: int,
        now: float,
    ) -> int:
        window_start = now - window_seconds
        timestamps = self._memory_ratelimit.get(mem_key, [])
        valid_timestamps = [ts for ts in timestamps if ts > window_start]
        if len(valid_timestamps) >= max_requests:
            oldest_ts = valid_timestamps[0]
            return max(1, int(oldest_ts + window_seconds - now))
        valid_timestamps.append(now)
        self._memory_ratelimit[mem_key] = valid_timestamps
        return 0

    async def _check_sliding_window(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> int:
        """Evaluate sliding window via AuthRateLimiterPort, Valkey, or memory."""
        if self._rate_limiter is not None:
            result = await self._rate_limiter.verificar_e_incrementar(
                chave=key,
                limite=max_requests,
                janela_segundos=window_seconds,
            )
            if result.permitido:
                return 0
            return max(1, result.retry_after_segundos)

        now = time.time()
        valkey_res = await self._valkey_sliding_window(
            key, max_requests, window_seconds, now
        )
        if valkey_res is not None:
            return valkey_res
        return self._memory_sliding_window(key, max_requests, window_seconds, now)

    async def _enforce_ip_rate_limit(
        self,
        *,
        namespace: str,
        client_ip: str,
        max_requests: int,
        window_seconds: int,
        action_label: str,
    ) -> None:
        clean_ip = client_ip.strip() or "127.0.0.1"
        ip_key = f"ratelimit:{namespace}:ip:{clean_ip}"
        retry_after = await self._check_sliding_window(
            key=ip_key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        if retry_after > 0:
            raise IdentificacaoRateLimitExcedidoError(
                f"Limite de solicitações de {action_label} excedido para "
                f"IP '{clean_ip}'. Tente novamente em {retry_after}s.",
                retry_after_segundos=retry_after,
            )

    async def _enforce_otp_rate_limit(self, clean_telefone: str) -> None:
        """Enforce maximum 3 OTP requests per 15-minute window using hashed PII."""
        phone_hash = _hash_pii_key(clean_telefone)
        retry_after = await self._check_sliding_window(
            key=f"ratelimit:otp:request:{phone_hash}",
            max_requests=OTP_MAX_REQUESTS_PER_WINDOW,
            window_seconds=OTP_RATE_LIMIT_WINDOW,
        )
        if retry_after > 0:
            tel_mask = _mascarar_telefone(clean_telefone)
            raise OtpRateLimitExcedidoError(
                f"Limite de solicitações de OTP excedido para o telefone '{tel_mask}'. "
                f"Tente novamente em {retry_after}s.",
                retry_after_segundos=retry_after,
            )

    async def _save_otp(
        self,
        clean_telefone: str,
        code_hash: str,
        paciente_id: UUID,
    ) -> None:
        """Store OTP state with 5-minute TTL."""
        data = {
            "code_hash": code_hash,
            "paciente_id": str(paciente_id),
            "attempts": 0,
            "expires_at": time.time() + OTP_TTL_SECONDS,
        }
        if self._valkey is not None:
            try:
                await self._valkey.set(  # pyright: ignore[reportUnknownMemberType]
                    f"otp:{clean_telefone}",
                    json.dumps(data),
                    ex=OTP_TTL_SECONDS,
                )
                return
            except Exception as exc:
                logger.warning(
                    "Valkey set failed, falling back to in-memory store: %s", exc
                )

        self._memory_otp[clean_telefone] = data

    async def _get_valkey_otp(self, clean_telefone: str) -> dict[str, Any] | None:
        if self._valkey is None:
            return None
        try:
            raw: bytes | str | None = await self._valkey.get(f"otp:{clean_telefone}")  # pyright: ignore[reportUnknownMemberType]
            if raw is None:
                return None
            raw_str = (
                raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
            )
            return json.loads(raw_str)  # type: ignore[no-any-return]
        except Exception as exc:
            logger.warning(
                "Valkey get failed, falling back to in-memory store: %s", exc
            )
            return None

    async def _get_otp(self, clean_telefone: str) -> dict[str, Any] | None:
        """Retrieve stored OTP state if not expired."""
        if self._valkey is not None:
            valkey_data = await self._get_valkey_otp(clean_telefone)
            if valkey_data is not None:
                return valkey_data

        item = self._memory_otp.get(clean_telefone)
        if item is None:
            return None
        if time.time() > float(item.get("expires_at", 0)):
            self._memory_otp.pop(clean_telefone, None)
            return None
        return item

    async def _update_valkey_attempts(
        self, clean_telefone: str, data: dict[str, Any]
    ) -> bool:
        if self._valkey is None:
            return False
        try:
            ttl = await self._valkey.ttl(f"otp:{clean_telefone}")  # pyright: ignore[reportUnknownMemberType]
            if ttl > 0:
                await self._valkey.set(  # pyright: ignore[reportUnknownMemberType]
                    f"otp:{clean_telefone}",
                    json.dumps(data),
                    ex=ttl,
                )
            return True
        except Exception as exc:
            logger.warning("Valkey attempt update failed: %s", exc)
            return False

    async def _update_attempts(self, clean_telefone: str, data: dict[str, Any]) -> None:
        """Increment failed attempts count while preserving remaining TTL."""
        if self._valkey is not None:
            updated = await self._update_valkey_attempts(clean_telefone, data)
            if updated:
                return

        if clean_telefone in self._memory_otp:
            self._memory_otp[clean_telefone] = data

    async def _delete_otp(self, clean_telefone: str) -> None:
        """Remove OTP record after successful verification or lockout."""
        if self._valkey is not None:
            try:
                await self._valkey.delete(f"otp:{clean_telefone}")  # pyright: ignore[reportUnknownMemberType]
            except Exception as exc:
                logger.warning("Valkey delete failed: %s", exc)

        self._memory_otp.pop(clean_telefone, None)

    async def solicitar_otp(
        self,
        dados: SolicitarOtpInputDTO,
    ) -> SolicitarOtpOutputDTO:
        """Emite código OTP de 6 dígitos com rate limiting por telefone (janela 15m).

        Regras: RN-AUT-03, RN-AUT-04, ADR-012, ADR-013, RF-01.
        Documentação: docs/explanation/domains/auth-domain.md
        """
        reader = self._require_identity_reader()

        clean_telefone = validate_telefone(dados.telefone)
        clean_cpf = validate_cpf(dados.cpf) if dados.cpf else None

        # 1. Enforce rate limiting before reading DB or generating OTP
        await self._enforce_otp_rate_limit(clean_telefone)

        # 2. Look up patient record via IdentityReaderPort
        paciente = await reader.buscar_paciente_por_telefone(
            telefone=clean_telefone,
            cpf=clean_cpf,
        )
        if paciente is None:
            return SolicitarOtpOutputDTO(
                mensagem="Código de verificação enviado com sucesso.",
                expira_em_segundos=OTP_TTL_SECONDS,
                codigo_debug=None,
            )

        # 3. Generate cryptographically secure 6-digit OTP
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()

        # 4. Save hash and patient info in Valkey with 5-minute TTL
        await self._save_otp(
            clean_telefone=clean_telefone,
            code_hash=code_hash,
            paciente_id=paciente.id,
        )

        # 5. Dispatch OTP via SMS port
        if self._sms_sender is not None:
            await self._sms_sender.enviar_otp(clean_telefone, codigo)

        codigo_debug = codigo if self._expose_debug_otp else None

        return SolicitarOtpOutputDTO(
            mensagem="Código de verificação enviado com sucesso.",
            expira_em_segundos=OTP_TTL_SECONDS,
            codigo_debug=codigo_debug,
        )

    async def verificar_otp(
        self,
        dados: VerificarOtpInputDTO,
    ) -> VerificarOtpOutputDTO:
        """Valida OTP em tempo constante e emite JWT de paciente (Role.PACIENTE).

        Regras: RN-AUT-03, RN-AUT-04, ADR-012, ADR-013, RF-01.
        Documentação: docs/explanation/domains/auth-domain.md
        """
        clean_telefone = validate_telefone(dados.telefone)
        tel_mask = _mascarar_telefone(clean_telefone)
        codigo = dados.codigo.strip()
        if len(codigo) != 6 or not codigo.isdigit():
            raise OtpInvalidoOuExpiradoError(
                f"Código OTP '{codigo}' deve conter exatamente 6 dígitos numéricos."
            )

        # 1. Retrieve OTP state
        stored = await self._get_otp(clean_telefone)
        if stored is None:
            raise OtpInvalidoOuExpiradoError(
                f"Código OTP incorreto ou expirado para o telefone '{tel_mask}'."
            )

        # 2. Check failed attempts count to mitigate brute-force guessing
        attempts = int(stored.get("attempts", 0))
        if attempts >= OTP_MAX_VERIFY_ATTEMPTS:
            await self._delete_otp(clean_telefone)
            raise OtpTentativasExcedidasError(
                f"Número máximo de {OTP_MAX_VERIFY_ATTEMPTS} tentativas de "
                f"validação excedido para o telefone '{tel_mask}'. "
                f"Código invalidado; tente novamente em {OTP_RATE_LIMIT_WINDOW}s.",
                retry_after_segundos=OTP_RATE_LIMIT_WINDOW,
            )

        # 3. Compare hash in constant time
        expected_hash = str(stored.get("code_hash", ""))
        input_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()

        if not hmac.compare_digest(expected_hash, input_hash):
            nova_tentativa = attempts + 1
            stored["attempts"] = nova_tentativa
            if nova_tentativa >= OTP_MAX_VERIFY_ATTEMPTS:
                await self._delete_otp(clean_telefone)
                raise OtpTentativasExcedidasError(
                    f"Número máximo de {OTP_MAX_VERIFY_ATTEMPTS} tentativas de "
                    f"validação excedido para o telefone '{tel_mask}'. "
                    f"Código invalidado; tente novamente em {OTP_RATE_LIMIT_WINDOW}s.",
                    retry_after_segundos=OTP_RATE_LIMIT_WINDOW,
                )
            await self._update_attempts(clean_telefone, stored)
            tentativas_restantes = max(0, OTP_MAX_VERIFY_ATTEMPTS - nova_tentativa)
            raise OtpInvalidoOuExpiradoError(
                f"Código OTP incorreto para o telefone '{tel_mask}'. "
                f"Restam {tentativas_restantes} tentativa(s) antes do bloqueio."
            )

        # 4. Successful verification: remove OTP immediately to prevent replay
        await self._delete_otp(clean_telefone)

        # 5. Issue lightweight JWT access token with Role.PACIENTE
        paciente_id = UUID(str(stored["paciente_id"]))
        atendimento_id = await self._resolve_active_attendance(paciente_id)
        token = create_access_token(
            usuario_id=paciente_id,
            papel=Role.PACIENTE.value,
            secret_key=self._secret_key,
            algorithm=self._algorithm,
            expire_minutes=self._access_token_expire_minutes,
        )

        return VerificarOtpOutputDTO(
            access_token=token,
            token_type="bearer",  # noqa: S106
            expires_in=self._access_token_expire_minutes * 60,
            paciente_id=paciente_id,
            role=Role.PACIENTE.value,
            atendimento_id=atendimento_id,
        )

    async def autenticar_cadsus_govbr(
        self,
        cpf: str | None = None,
        data_nascimento: date | None = None,
        cns: str | None = None,
        nome_mae: str | None = None,
    ) -> VerificarOtpOutputDTO:
        """Autenticação sem senha via CADSUS/Gov.br por desambiguação de dados civis.

        Regras: RN-AUT-09, ADR-012, ADR-013, RF-01, CFM nº 2.314/2022 e
        docs/explanation/domains/auth-domain.md.
        """
        reader = self._require_identity_reader()

        clean_cpf = validate_cpf(cpf) if cpf else None
        clean_cns = cns.strip() if cns and cns.strip() else None

        if not clean_cpf and not clean_cns:
            raise PacienteNaoEncontradoError(
                f"Desambiguação CADSUS inválida (recebido cpf={cpf!r}, "
                f"cns={cns!r}); esperado ao menos CPF (11 dígitos) ou CNS "
                "(15 dígitos) válido para autenticação sem senha."
            )

        paciente = await reader.buscar_paciente_cadsus(
            cpf=clean_cpf,
            data_nascimento=data_nascimento,
            cns=clean_cns,
            nome_mae=nome_mae,
        )
        if paciente is None:
            cpf_masked = mascarar_cpf(clean_cpf) if clean_cpf else "N/A"
            cns_masked = mascarar_cns(clean_cns) if clean_cns else "N/A"
            raise PacienteNaoEncontradoError(
                "Paciente com dados civis informados "
                f"(CPF: {cpf_masked}, CNS: {cns_masked}) "
                "não encontrado na plataforma."
            )

        token = create_access_token(
            usuario_id=paciente.id,
            papel=Role.PACIENTE.value,
            secret_key=self._secret_key,
            algorithm=self._algorithm,
            expire_minutes=self._access_token_expire_minutes,
        )

        return VerificarOtpOutputDTO(
            access_token=token,
            token_type="bearer",  # noqa: S106
            expires_in=self._access_token_expire_minutes * 60,
            paciente_id=paciente.id,
            role=Role.PACIENTE.value,
        )

    def _require_identity_reader(self) -> IdentityReaderPort:
        if self._identity_reader is None:
            raise ValueError(
                f"IdentityReaderPort não configurado no PatientAuthService "
                f"(recebido: {self._identity_reader!r}; esperado instância de "
                "IdentityReaderPort)."
            )
        return self._identity_reader

    def _require_identity_writer(self) -> IdentityWriterPort:
        if self._identity_writer is None:
            raise ValueError(
                f"IdentityWriterPort não configurado no PatientAuthService "
                f"(recebido: {self._identity_writer!r}; esperado instância de "
                "IdentityWriterPort)."
            )
        return self._identity_writer

    def _require_credential_repo(self) -> PatientCredentialRepositoryPort:
        if self._credential_repo is None:
            raise ValueError(
                "PatientCredentialRepositoryPort não configurado no PatientAuthService "
                f"(recebido: {self._credential_repo!r}; esperado repositório de "
                "credenciais)."
            )
        return self._credential_repo

    def _require_password_hasher(self) -> PasswordHasherPort:
        if self._password_hasher is None:
            raise ValueError(
                f"PasswordHasherPort não configurado no PatientAuthService "
                f"(recebido: {self._password_hasher!r}; esperado instância de "
                "PasswordHasherPort)."
            )
        return self._password_hasher

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise ValueError(
                f"AsyncSession não configurada no PatientAuthService "
                f"(recebido: {self._session!r}; esperado instância de AsyncSession)."
            )
        return self._session

    def _validate_registration_payload(
        self, dados: RegistrarPacienteCommand
    ) -> tuple[str, str, str, str, str | None]:
        if not dados.aceite_privacidade:
            raise ValidationError(
                "Aceite da política de privacidade (LGPD) é obrigatório "
                f"(recebido aceite_privacidade={dados.aceite_privacidade!r}; "
                "esperado True)."
            )

        clean_cpf = validate_cpf(dados.cpf)
        clean_telefone = validate_telefone(dados.telefone)
        clean_nome = dados.nome_completo.strip()
        if len(clean_nome) < 2:
            raise ValidationError(
                f"Nome completo '{clean_nome}' inválido ({len(clean_nome)} chars); "
                "esperado ao menos 2 caracteres."
            )

        if dados.data_nascimento > date.today():
            raise ValidationError(
                f"Data de nascimento '{dados.data_nascimento}' não pode ser futura "
                f"(hoje: {date.today()})."
            )

        clean_email = dados.email.strip().lower()
        if not clean_email or not _EMAIL_RE.match(clean_email):
            raise ValidationError(
                f"E-mail '{clean_email}' inválido; esperado formato 'usuario@dominio'."
            )

        clean_senha = dados.senha
        if clean_senha is not None and len(clean_senha.strip()) < 8:
            raise ValidationError(
                f"Senha informada possui {len(clean_senha.strip())} caractere(s); "
                "esperado mínimo de 8 caracteres."
            )

        return clean_cpf, clean_telefone, clean_nome, clean_email, clean_senha

    async def _validate_and_build_credential_spec(
        self,
        *,
        clean_email: str,
        clean_senha: str | None,
    ) -> tuple[str, str]:
        cred_repo = self._require_credential_repo()
        if await cred_repo.existe_identificador(clean_email):
            if clean_senha is not None:
                hasher = self._require_password_hasher()
                await asyncio.to_thread(hasher.dummy_verify)
            logger.warning("Conflito de identificador no cadastro de paciente.")
            raise ConflictError(
                "Não foi possível concluir o cadastro com os dados informados. "
                "Caso já possua conta, utilize a opção Entrar."
            )

        if clean_senha is None:
            return clean_email, f"{UNUSABLE_CREDENTIAL_MARKER}{secrets.token_hex(16)}"

        hasher = self._require_password_hasher()
        senha_hash = await asyncio.to_thread(hasher.hash, clean_senha)
        return clean_email, senha_hash

    async def _dispatch_initial_otp(
        self, clean_telefone: str, clean_cpf: str
    ) -> tuple[bool, int, str | None]:
        try:
            otp_out = await self.solicitar_otp(
                dados=SolicitarOtpInputDTO(telefone=clean_telefone, cpf=clean_cpf),
            )
            return True, otp_out.expira_em_segundos, otp_out.codigo_debug
        except OtpRateLimitExcedidoError:
            return False, OTP_TTL_SECONDS, None

    async def registrar_paciente(
        self,
        command: RegistrarPacienteCommand,
    ) -> RegistrarPacienteOutputDTO:
        """Registra novo paciente (cidadão) com e-mail obrigatório e envia OTP inicial.

        Regras: RN-AUT-09, ADR-012, ADR-013, RF-01, LGPD Art. 11 e
        docs/explanation/domains/auth-domain.md.
        """
        session = self._require_session()
        writer = self._require_identity_writer()
        cred_repo = self._require_credential_repo()

        await self._enforce_ip_rate_limit(
            namespace="patient_reg",
            client_ip=command.client_ip,
            max_requests=REGISTER_MAX_REQUESTS_PER_IP,
            window_seconds=REGISTER_RATE_LIMIT_WINDOW,
            action_label="cadastro",
        )

        (
            clean_cpf,
            clean_telefone,
            clean_nome,
            clean_email,
            clean_senha,
        ) = self._validate_registration_payload(command)

        identificador, senha_hash = await self._validate_and_build_credential_spec(
            clean_email=clean_email,
            clean_senha=clean_senha,
        )

        paciente = await writer.criar_paciente(
            cpf=clean_cpf,
            nome_completo=clean_nome,
            data_nascimento=command.data_nascimento,
            telefone=clean_telefone,
        )

        await cred_repo.criar_credencial(
            UsuarioCredencial(
                usuario_id=paciente.id,
                identificador=identificador,
                senha_hash=senha_hash,
                papel=Role.PACIENTE.value,
                ativo=True,
                mfa_ativo=False,
            )
        )

        await session.commit()

        otp_enviado, expira_em, codigo_debug = await self._dispatch_initial_otp(
            clean_telefone=clean_telefone,
            clean_cpf=clean_cpf,
        )
        return RegistrarPacienteOutputDTO(
            paciente_id=paciente.id,
            telefone_mascarado=_mascarar_telefone(clean_telefone),
            otp_enviado=otp_enviado,
            expira_em_segundos=expira_em,
            codigo_debug=codigo_debug,
        )

    async def _enforce_identify_rate_limit(
        self,
        client_ip: str,
        normalized_ident: str,
    ) -> None:
        ident_hash = _hash_pii_key(normalized_ident)
        checks = (
            (
                f"ratelimit:identify:ip:{client_ip}",
                IDENTIFY_MAX_REQUESTS_PER_IP,
            ),
            (
                f"ratelimit:identify:id:{ident_hash}",
                IDENTIFY_MAX_REQUESTS_PER_IDENT,
            ),
        )
        for key, max_req in checks:
            retry_after = await self._check_sliding_window(
                key=key,
                max_requests=max_req,
                window_seconds=IDENTIFY_RATE_LIMIT_WINDOW,
            )
            if retry_after > 0:
                raise IdentificacaoRateLimitExcedidoError(
                    f"Limite de solicitações de identificação excedido para "
                    f"IP '{client_ip}'. Tente novamente em {retry_after}s.",
                    retry_after_segundos=retry_after,
                )

    def _parse_patient_identifier(
        self, raw_identificador: str
    ) -> tuple[str | None, str | None]:
        cleaned = raw_identificador.strip()
        if "@" in cleaned:
            email_lower = cleaned.lower()
            if not _EMAIL_RE.match(email_lower):
                raise ValidationError(
                    f"Identificador de e-mail '{email_lower}' inválido; "
                    "esperado formato 'usuario@dominio'."
                )
            return None, email_lower

        digits = re.sub(r"\D", "", cleaned)
        if len(digits) == 11:
            return digits, None

        raise ValidationError(
            f"Identificador '{cleaned}' inválido; esperado CPF (11 dígitos) "
            "ou endereço de e-mail válido."
        )

    async def _resolve_patient_and_credential(
        self,
        clean_cpf: str | None,
        clean_email: str | None,
    ) -> tuple[PacienteAuthLookupDTO | None, UsuarioCredencial | None]:
        reader = self._require_identity_reader()
        if clean_cpf is not None:
            paciente = await reader.buscar_paciente_cadsus(cpf=clean_cpf)
            cred = None
            if paciente is not None and self._credential_repo is not None:
                cred = await self._credential_repo.buscar_por_usuario_id(
                    paciente.id, Role.PACIENTE.value
                )
            return paciente, cred

        if clean_email is None or self._credential_repo is None:
            return None, None

        cred = await self._credential_repo.buscar_por_identificador(
            clean_email, Role.PACIENTE.value
        )
        if cred is None:
            return None, None
        paciente = await reader.buscar_paciente_por_id(cred.usuario_id)
        return paciente, cred

    async def _collect_patient_methods(
        self,
        paciente: PacienteAuthLookupDTO,
        cred: UsuarioCredencial | None,
    ) -> list[Literal["otp", "senha", "passkey", "govbr"]]:
        reader = self._require_identity_reader()
        metodos: list[Literal["otp", "senha", "passkey", "govbr"]] = []
        if paciente.telefone:
            metodos.append("otp")
        if (
            cred is not None
            and cred.ativo
            and not cred.senha_hash.startswith(UNUSABLE_CREDENTIAL_MARKER)
        ):
            metodos.append("senha")
        passkeys = await reader.listar_passkeys_paciente(paciente.id)
        if passkeys:
            metodos.append("passkey")
        if self._govbr_oidc_enabled:
            metodos.append("govbr")
        return metodos

    async def identificar_paciente(
        self,
        command: IdentificarPacienteCommand,
    ) -> IdentificarPacienteOutputDTO:
        """Identifica métodos de autenticação disponíveis sem vazar PII ou enumeração.

        Regras: RN-AUT-09 (Anti-Enumeração), ADR-012, ADR-013, RF-01 e
        docs/explanation/domains/auth-domain.md.
        """
        _ = self._require_identity_reader()
        clean_cpf, clean_email = self._parse_patient_identifier(command.identificador)
        normalized_key = clean_cpf if clean_cpf is not None else str(clean_email)

        await self._enforce_identify_rate_limit(command.client_ip, normalized_key)

        paciente, cred = await self._resolve_patient_and_credential(
            clean_cpf, clean_email
        )
        if paciente is None:
            metodos_absent: list[Literal["otp", "senha", "passkey", "govbr"]] = (
                ["govbr"] if self._govbr_oidc_enabled else []
            )
            return IdentificarPacienteOutputDTO(
                possui_conta=False,
                metodos_disponiveis=metodos_absent,
                telefone_mascarado=None,
                govbr_habilitado=self._govbr_oidc_enabled,
            )

        metodos = await self._collect_patient_methods(paciente, cred)
        tel_mask = _mascarar_telefone(paciente.telefone) if paciente.telefone else None
        return IdentificarPacienteOutputDTO(
            possui_conta=True,
            metodos_disponiveis=metodos,
            telefone_mascarado=tel_mask,
            govbr_habilitado=self._govbr_oidc_enabled,
        )

    async def _resolve_credential_for_password_login(
        self, raw_identificador: str
    ) -> UsuarioCredencial | None:
        cred_repo = self._require_credential_repo()
        cleaned = raw_identificador.strip()
        if "@" in cleaned:
            return await cred_repo.buscar_por_identificador(
                cleaned.lower(), Role.PACIENTE.value
            )

        clean_cpf = validate_cpf(cleaned)
        if self._identity_reader is None:
            return None

        paciente = await self._identity_reader.buscar_paciente_cadsus(cpf=clean_cpf)
        if paciente is None:
            return None
        return await cred_repo.buscar_por_usuario_id(paciente.id, Role.PACIENTE.value)

    async def _verify_patient_password_or_lockout(
        self, cred: UsuarioCredencial, senha: str
    ) -> Literal["ok", "invalid", "locked"]:
        hasher = self._require_password_hasher()
        is_valida = await asyncio.to_thread(hasher.verify, senha, cred.senha_hash)
        if is_valida:
            cred.registrar_sucesso_login()
            if hasher.needs_rehash(cred.senha_hash):
                novo_hash = await asyncio.to_thread(hasher.hash, senha)
                cred.atualizar_senha(novo_hash)
            return "ok"

        recem_bloqueado = cred.registrar_falha_login(
            max_falhas=PASSWORD_MAX_FAILURES,
            minutos_bloqueio=PASSWORD_LOCKOUT_MINUTES,
        )
        return "locked" if recem_bloqueado else "invalid"

    async def autenticar_paciente_senha(
        self,
        command: LoginPacienteSenhaCommand,
    ) -> VerificarOtpOutputDTO:
        """Autentica paciente via senha Argon2id com lockout sem exigir MFA TOTP.

        Regras: RN-AUT-02 (Lockout), RN-AUT-09, ADR-012, ADR-013, RF-01 e
        docs/explanation/domains/auth-domain.md.
        """
        session = self._require_session()
        _ = self._require_credential_repo()
        hasher = self._require_password_hasher()

        await self._enforce_ip_rate_limit(
            namespace="patient_pwd",
            client_ip=command.client_ip,
            max_requests=PASSWORD_MAX_FAILURES * 3,
            window_seconds=OTP_RATE_LIMIT_WINDOW,
            action_label="autenticação",
        )

        cred = await self._resolve_credential_for_password_login(command.identificador)
        if cred is None or cred.senha_hash.startswith(UNUSABLE_CREDENTIAL_MARKER):
            await asyncio.to_thread(hasher.dummy_verify)
            raise CredenciaisInvalidasError()

        if not cred.ativo:
            await asyncio.to_thread(hasher.dummy_verify)
            raise ContaDesativadaError()

        if cred.is_bloqueado():
            await asyncio.to_thread(hasher.dummy_verify)
            raise ContaBloqueadaError()

        outcome = await self._verify_patient_password_or_lockout(cred, command.senha)
        await session.commit()
        if outcome == "locked":
            raise ContaBloqueadaError()
        if outcome == "invalid":
            raise CredenciaisInvalidasError()

        paciente_id = cred.usuario_id
        atendimento_id = await self._resolve_active_attendance(paciente_id)
        token = create_access_token(
            usuario_id=paciente_id,
            papel=Role.PACIENTE.value,
            secret_key=self._secret_key,
            algorithm=self._algorithm,
            expire_minutes=self._access_token_expire_minutes,
        )
        return VerificarOtpOutputDTO(
            access_token=token,
            token_type="bearer",  # noqa: S106
            expires_in=self._access_token_expire_minutes * 60,
            paciente_id=paciente_id,
            role=Role.PACIENTE.value,
            atendimento_id=atendimento_id,
        )

    def obter_capacidades_metodos(self) -> MetodosAutenticacaoPacienteOutputDTO:
        """Retorna capacidades habilitadas de login do paciente conforme settings.

        Regras: ADR-009 (Configurações Desacopladas), RF-01 e
        docs/explanation/domains/auth-domain.md.
        """
        return MetodosAutenticacaoPacienteOutputDTO(
            govbr_oidc_enabled=self._govbr_oidc_enabled,
            passkeys_enabled=True,
            otp_enabled=True,
            password_fallback_enabled=True,
        )
