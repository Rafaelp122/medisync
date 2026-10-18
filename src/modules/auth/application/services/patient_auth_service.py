"""Application service orchestrating passwordless patient OTP authentication."""

import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from src.core.authz.roles import Role
from src.core.authz.token import create_access_token
from src.core.errors import TenantInvalidoError
from src.core.uuid7 import uuid7
from src.modules.auth.application.dtos import (
    SolicitarOtpInputDTO,
    SolicitarOtpOutputDTO,
    VerificarOtpInputDTO,
    VerificarOtpOutputDTO,
)
from src.modules.auth.application.ports.identity_reader_port import (
    IdentityReaderPort,
)
from src.modules.auth.application.ports.sms_sender_port import (
    SmsSenderPort,
)
from src.modules.auth.domain.exceptions import (
    OtpInvalidoOuExpiradoError,
    OtpRateLimitExcedidoError,
    PacienteNaoEncontradoError,
)
from src.modules.auth.domain.validators import validate_cpf, validate_telefone

logger = logging.getLogger("medisync.auth.patient_auth")

OTP_TTL_SECONDS = 300  # 5 minutes validity
OTP_RATE_LIMIT_WINDOW = 900  # 15 minutes window
OTP_MAX_REQUESTS_PER_WINDOW = 3
OTP_MAX_VERIFY_ATTEMPTS = 3


def _mascarar_telefone(clean_telefone: str) -> str:
    """Mask phone number for safe exception display without leaking PII."""
    if len(clean_telefone) >= 8:
        return f"{clean_telefone[:4]}****{clean_telefone[-4:]}"
    return "****"


class PatientAuthService:
    """Autenticação sem senha de pacientes via código OTP de 6 dígitos por SMS.

    Regras: ADR-005 (Passwordless + Argon2id/OTP), RF-01.
    Documentação: docs/explanation/domains/auth-domain.md e
    docs/adrs/ADR-005-Autenticacao-Passwordless-Argon2id.md
    """

    def __init__(
        self,
        identity_reader: IdentityReaderPort | None = None,
        valkey_client: Redis | None = None,
        sms_sender: SmsSenderPort | None = None,
        secret_key: str | None = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
        is_debug: bool = True,
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
        self._is_debug = is_debug
        # In-memory storage fallback for unit testing when Valkey is None
        self._memory_otp: dict[str, dict[str, Any]] = {}
        self._memory_ratelimit: dict[str, list[float]] = {}

    async def _calculate_valkey_retry_after(self, redis_key: str, now: float) -> int:
        """Calculate seconds remaining until the oldest entry slides out of window."""
        if self._valkey is None:
            return OTP_RATE_LIMIT_WINDOW
        oldest_entries: list[Any] = await self._valkey.zrange(  # pyright: ignore[reportUnknownMemberType]
            redis_key, 0, 0, withscores=True
        )
        if not oldest_entries:
            return OTP_RATE_LIMIT_WINDOW
        oldest_time = float(oldest_entries[0][1])
        return max(1, int(oldest_time + OTP_RATE_LIMIT_WINDOW - now))

    async def _check_valkey_rate_limit(
        self, redis_key: str, clean_telefone: str, now: float, window_start: float
    ) -> bool:
        """Evaluate rate limit via Valkey sliding window.

        Returns True if handled, False on fallback.
        """
        if self._valkey is None:
            return False

        try:
            async with self._valkey.pipeline(transaction=True) as pipe:
                await pipe.zremrangebyscore(redis_key, 0, window_start)  # pyright: ignore[reportUnknownMemberType]
                await pipe.zcard(redis_key)  # pyright: ignore[reportUnknownMemberType]
                results: list[Any] = await pipe.execute()  # pyright: ignore[reportUnknownMemberType]

            current_count = int(results[1])
            if current_count >= OTP_MAX_REQUESTS_PER_WINDOW:
                retry_after = await self._calculate_valkey_retry_after(redis_key, now)
                tel_mask = _mascarar_telefone(clean_telefone)
                raise OtpRateLimitExcedidoError(
                    f"Limite de solicitações de OTP excedido para o "
                    f"telefone '{tel_mask}'. Tente novamente em {retry_after}s."
                )

            attempt_id = str(uuid7())
            async with self._valkey.pipeline(transaction=True) as pipe:
                await pipe.zadd(redis_key, {attempt_id: now})  # pyright: ignore[reportUnknownMemberType]
                await pipe.expire(redis_key, OTP_RATE_LIMIT_WINDOW + 60)  # pyright: ignore[reportUnknownMemberType]
                await pipe.execute()  # pyright: ignore[reportUnknownMemberType]
            return True
        except OtpRateLimitExcedidoError:
            raise
        except Exception as exc:
            logger.warning("Valkey rate limit failed, falling back to memory: %s", exc)
            return False

    def _check_memory_rate_limit(
        self, clean_telefone: str, now: float, window_start: float
    ) -> None:
        """In-memory rate limit check for unit test fallback."""
        timestamps = self._memory_ratelimit.get(clean_telefone, [])
        valid_timestamps = [ts for ts in timestamps if ts > window_start]
        if len(valid_timestamps) >= OTP_MAX_REQUESTS_PER_WINDOW:
            oldest_ts = valid_timestamps[0]
            retry_after = max(1, int(oldest_ts + OTP_RATE_LIMIT_WINDOW - now))
            tel_mask = _mascarar_telefone(clean_telefone)
            raise OtpRateLimitExcedidoError(
                f"Limite de solicitações de OTP excedido para o telefone '{tel_mask}'. "
                f"Tente novamente em {retry_after} segundos."
            )
        valid_timestamps.append(now)
        self._memory_ratelimit[clean_telefone] = valid_timestamps

    async def _check_rate_limit(self, clean_telefone: str) -> None:
        """Enforce maximum 3 OTP requests per 15-minute window."""
        now = time.time()
        window_start = now - OTP_RATE_LIMIT_WINDOW
        redis_key = f"ratelimit:otp:request:{clean_telefone}"

        if await self._check_valkey_rate_limit(
            redis_key, clean_telefone, now, window_start
        ):
            return

        self._check_memory_rate_limit(clean_telefone, now, window_start)

    async def _save_otp(
        self,
        clean_telefone: str,
        code_hash: str,
        paciente_id: UUID,
        organizacao_id: int,
    ) -> None:
        """Store OTP state with 5-minute TTL."""
        data = {
            "code_hash": code_hash,
            "paciente_id": str(paciente_id),
            "organizacao_id": organizacao_id,
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
        organizacao_id: int,
        dados: SolicitarOtpInputDTO,
    ) -> SolicitarOtpOutputDTO:
        """Emite código OTP de 6 dígitos com rate limiting por telefone (janela 15m).

        Regras: ADR-005 (Passwordless SMS OTP), RF-01.
        Documentação: docs/explanation/domains/auth-domain.md
        """
        if self._identity_reader is None:
            raise ValueError(
                "IdentityReaderPort não configurado no PatientAuthService."
            )
        if organizacao_id <= 0:
            raise TenantInvalidoError(
                f"Identificador da organização '{organizacao_id}' deve ser "
                "positivo; esperado valor > 0."
            )

        clean_telefone = validate_telefone(dados.telefone)
        clean_cpf = validate_cpf(dados.cpf) if dados.cpf else None

        # 1. Enforce rate limiting before reading DB or generating OTP
        await self._check_rate_limit(clean_telefone)

        # 2. Look up patient record within organization via IdentityReaderPort
        paciente = await self._identity_reader.buscar_paciente_por_telefone(
            organizacao_id=organizacao_id,
            telefone=clean_telefone,
            cpf=clean_cpf,
        )
        if paciente is None:
            tel_mask = _mascarar_telefone(clean_telefone)
            raise PacienteNaoEncontradoError(
                f"Paciente com telefone '{tel_mask}' não encontrado na "
                f"organização '{organizacao_id}'. Inicie o acolhimento para "
                "cadastrar-se."
            )

        # 3. Generate cryptographically secure 6-digit OTP
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()

        # 4. Save hash and patient info in Valkey with 5-minute TTL
        await self._save_otp(
            clean_telefone=clean_telefone,
            code_hash=code_hash,
            paciente_id=paciente.id,
            organizacao_id=organizacao_id,
        )

        # 5. Dispatch OTP via SMS port
        if self._sms_sender is not None:
            await self._sms_sender.enviar_otp(clean_telefone, codigo)

        codigo_debug = codigo if self._is_debug else None

        return SolicitarOtpOutputDTO(
            mensagem="Código de verificação enviado com sucesso.",
            expira_em_segundos=OTP_TTL_SECONDS,
            codigo_debug=codigo_debug,
        )

    async def verificar_otp(
        self,
        organizacao_id: int,
        dados: VerificarOtpInputDTO,
    ) -> VerificarOtpOutputDTO:
        """Valida OTP em tempo constante e emite JWT de paciente (Role.PACIENTE).

        Regras: ADR-005 (Passwordless SMS OTP), RF-01.
        Documentação: docs/explanation/domains/auth-domain.md
        """
        if organizacao_id <= 0:
            raise TenantInvalidoError(
                f"Identificador da organização '{organizacao_id}' deve ser "
                "positivo; esperado valor > 0."
            )

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

        stored_org_id = int(stored.get("organizacao_id", 0))
        if stored_org_id != organizacao_id:
            raise OtpInvalidoOuExpiradoError(
                f"Código OTP incorreto ou expirado: pertence à organização "
                f"'{stored_org_id}', mas a requisição é da organização "
                f"'{organizacao_id}'."
            )

        # 2. Check failed attempts count to mitigate brute-force guessing
        attempts = int(stored.get("attempts", 0))
        if attempts >= OTP_MAX_VERIFY_ATTEMPTS:
            await self._delete_otp(clean_telefone)
            raise OtpInvalidoOuExpiradoError(
                f"Número máximo de {OTP_MAX_VERIFY_ATTEMPTS} tentativas excedido "
                f"para o telefone '{tel_mask}'. Solicite um novo código."
            )

        # 3. Compare hash in constant time
        expected_hash = str(stored.get("code_hash", ""))
        input_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()

        if not hmac.compare_digest(expected_hash, input_hash):
            nova_tentativa = attempts + 1
            stored["attempts"] = nova_tentativa
            if nova_tentativa >= OTP_MAX_VERIFY_ATTEMPTS:
                await self._delete_otp(clean_telefone)
                raise OtpInvalidoOuExpiradoError(
                    f"Número máximo de {OTP_MAX_VERIFY_ATTEMPTS} tentativas excedido "
                    f"para o telefone '{tel_mask}'. Solicite um novo código."
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
        token = create_access_token(
            usuario_id=paciente_id,
            organizacao_id=organizacao_id,
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
        )
