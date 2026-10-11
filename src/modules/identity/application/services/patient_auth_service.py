"""Application service orchestrating passwordless patient OTP authentication."""

import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select

from src.core.authz.roles import Role
from src.core.authz.token import create_access_token
from src.core.config import get_settings
from src.core.uuid7 import uuid7
from src.modules.identity.application.dtos import (
    SolicitarOtpInputDTO,
    SolicitarOtpOutputDTO,
    VerificarOtpInputDTO,
    VerificarOtpOutputDTO,
)
from src.modules.identity.application.ports.sms_sender_port import SmsSenderPort
from src.modules.identity.domain.exceptions import (
    OtpInvalidoOuExpiradoError,
    OtpRateLimitExcedidoError,
    PacienteNaoEncontradoError,
    TenantInvalidoError,
)
from src.modules.identity.domain.models import Paciente
from src.modules.identity.domain.validators import validate_cpf, validate_telefone

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("medisync.identity.patient_auth")

OTP_TTL_SECONDS = 300  # 5 minutes validity
OTP_RATE_LIMIT_WINDOW = 900  # 15 minutes window
OTP_MAX_REQUESTS_PER_WINDOW = 3
OTP_MAX_VERIFY_ATTEMPTS = 3


class PatientAuthService:
    """Service handling passwordless patient authentication via 6-digit SMS OTP."""

    def __init__(
        self,
        session: "AsyncSession | None" = None,
        valkey_client: Redis | None = None,
        sms_sender: SmsSenderPort | None = None,
        secret_key: str | None = None,
        algorithm: str | None = None,
        access_token_expire_minutes: int | None = None,
    ) -> None:
        self._session = session
        self._valkey = valkey_client
        self._sms_sender = sms_sender
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_token_expire_minutes = access_token_expire_minutes
        # In-memory storage fallback for unit testing when Valkey is None
        self._memory_otp: dict[str, dict[str, Any]] = {}
        self._memory_ratelimit: dict[str, list[float]] = {}

    async def _check_rate_limit(self, clean_telefone: str) -> None:
        """Enforce maximum 3 OTP requests per 15-minute window."""
        now = time.time()
        window_start = now - OTP_RATE_LIMIT_WINDOW

        if self._valkey is not None:
            redis_key = f"ratelimit:otp:request:{clean_telefone}"
            try:
                async with self._valkey.pipeline(transaction=True) as pipe:
                    await pipe.zremrangebyscore(redis_key, 0, window_start)  # pyright: ignore[reportUnknownMemberType]
                    await pipe.zcard(redis_key)  # pyright: ignore[reportUnknownMemberType]
                    results: list[Any] = await pipe.execute()  # pyright: ignore[reportUnknownMemberType]

                current_count = int(results[1])
                if current_count >= OTP_MAX_REQUESTS_PER_WINDOW:
                    oldest_entries: list[Any] = await self._valkey.zrange(  # pyright: ignore[reportUnknownMemberType]
                        redis_key, 0, 0, withscores=True
                    )
                    retry_after = OTP_RATE_LIMIT_WINDOW
                    if oldest_entries:
                        oldest_time = float(oldest_entries[0][1])
                        retry_after = max(
                            1, int(oldest_time + OTP_RATE_LIMIT_WINDOW - now)
                        )
                    raise OtpRateLimitExcedidoError(
                        "Limite de solicitações de OTP excedido. "
                        f"Tente novamente em {retry_after} segundos."
                    )

                # Record attempt
                attempt_id = str(uuid7())
                async with self._valkey.pipeline(transaction=True) as pipe:
                    await pipe.zadd(redis_key, {attempt_id: now})  # pyright: ignore[reportUnknownMemberType]
                    await pipe.expire(redis_key, OTP_RATE_LIMIT_WINDOW + 60)  # pyright: ignore[reportUnknownMemberType]
                    await pipe.execute()  # pyright: ignore[reportUnknownMemberType]
                return
            except OtpRateLimitExcedidoError:
                raise
            except Exception as exc:
                logger.warning(
                    "Valkey rate limit failed, falling back to memory: %s", exc
                )

        # In-memory fallback
        timestamps = self._memory_ratelimit.get(clean_telefone, [])
        valid_timestamps = [ts for ts in timestamps if ts > window_start]
        if len(valid_timestamps) >= OTP_MAX_REQUESTS_PER_WINDOW:
            oldest_ts = valid_timestamps[0]
            retry_after = max(1, int(oldest_ts + OTP_RATE_LIMIT_WINDOW - now))
            raise OtpRateLimitExcedidoError(
                "Limite de solicitações de OTP excedido. "
                f"Tente novamente em {retry_after} segundos."
            )
        valid_timestamps.append(now)
        self._memory_ratelimit[clean_telefone] = valid_timestamps

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

    async def _get_otp(self, clean_telefone: str) -> dict[str, Any] | None:
        """Retrieve stored OTP state if not expired."""
        if self._valkey is not None:
            try:
                raw: bytes | str | None = await self._valkey.get(
                    f"otp:{clean_telefone}"
                )  # pyright: ignore[reportUnknownMemberType]
                if raw is not None:
                    raw_str = (
                        raw.decode("utf-8")
                        if isinstance(raw, (bytes, bytearray))
                        else raw
                    )
                    return json.loads(raw_str)  # type: ignore[no-any-return]
                return None
            except Exception as exc:
                logger.warning(
                    "Valkey get failed, falling back to in-memory store: %s", exc
                )

        item = self._memory_otp.get(clean_telefone)
        if item is not None:
            if time.time() > float(item.get("expires_at", 0)):
                self._memory_otp.pop(clean_telefone, None)
                return None
            return item
        return None

    async def _update_attempts(self, clean_telefone: str, data: dict[str, Any]) -> None:
        """Increment failed attempts count while preserving remaining TTL."""
        if self._valkey is not None:
            try:
                ttl = await self._valkey.ttl(f"otp:{clean_telefone}")  # pyright: ignore[reportUnknownMemberType]
                if ttl > 0:
                    await self._valkey.set(  # pyright: ignore[reportUnknownMemberType]
                        f"otp:{clean_telefone}",
                        json.dumps(data),
                        ex=ttl,
                    )
                return
            except Exception as exc:
                logger.warning("Valkey attempt update failed: %s", exc)

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
        session: "AsyncSession | None" = None,
    ) -> SolicitarOtpOutputDTO:
        """Execute request OTP use-case with rate limiting and patient lookup."""
        db = session or self._session
        if db is None:
            raise ValueError("AsyncSession não configurada no PatientAuthService.")
        if organizacao_id <= 0:
            raise TenantInvalidoError("Identificador da organização deve ser positivo.")

        clean_telefone = validate_telefone(dados.telefone)
        clean_cpf = validate_cpf(dados.cpf) if dados.cpf else None

        # 1. Enforce rate limiting before reading DB or generating OTP
        await self._check_rate_limit(clean_telefone)

        # 2. Look up patient record within organization
        stmt = select(Paciente).where(
            Paciente.organizacao_id == organizacao_id,
            Paciente.telefone == clean_telefone,
        )
        if clean_cpf:
            stmt = stmt.where(Paciente.cpf == clean_cpf)

        result = await db.execute(stmt)
        paciente = result.scalars().first()
        if paciente is None:
            raise PacienteNaoEncontradoError(
                "Paciente com o telefone informado não encontrado nesta organização. "
                "Inicie o acolhimento para cadastrar-se."
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

        settings = get_settings()
        codigo_debug = codigo if settings.DEBUG else None

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
        """Verify 6-digit OTP code and issue patient JWT."""
        if organizacao_id <= 0:
            raise TenantInvalidoError("Identificador da organização deve ser positivo.")

        clean_telefone = validate_telefone(dados.telefone)
        codigo = dados.codigo.strip()
        if len(codigo) != 6 or not codigo.isdigit():
            raise OtpInvalidoOuExpiradoError(
                "Código OTP deve conter exatamente 6 dígitos numéricos."
            )

        # 1. Retrieve OTP state
        stored = await self._get_otp(clean_telefone)
        if stored is None:
            raise OtpInvalidoOuExpiradoError("Código OTP incorreto ou expirado.")

        if int(stored.get("organizacao_id", 0)) != organizacao_id:
            raise OtpInvalidoOuExpiradoError("Código OTP incorreto ou expirado.")

        # 2. Check failed attempts count to mitigate brute-force guessing
        attempts = int(stored.get("attempts", 0))
        if attempts >= OTP_MAX_VERIFY_ATTEMPTS:
            await self._delete_otp(clean_telefone)
            raise OtpInvalidoOuExpiradoError(
                "Número máximo de tentativas excedido. Solicite um novo código."
            )

        # 3. Compare hash in constant time
        expected_hash = str(stored.get("code_hash", ""))
        input_hash = hashlib.sha256(codigo.encode("utf-8")).hexdigest()

        if not hmac.compare_digest(expected_hash, input_hash):
            stored["attempts"] = attempts + 1
            if stored["attempts"] >= OTP_MAX_VERIFY_ATTEMPTS:
                await self._delete_otp(clean_telefone)
                raise OtpInvalidoOuExpiradoError(
                    "Número máximo de tentativas excedido. Solicite um novo código."
                )
            await self._update_attempts(clean_telefone, stored)
            raise OtpInvalidoOuExpiradoError("Código OTP incorreto ou expirado.")

        # 4. Successful verification: remove OTP immediately to prevent replay
        await self._delete_otp(clean_telefone)

        # 5. Issue lightweight JWT access token with Role.PACIENTE
        paciente_id = UUID(str(stored["paciente_id"]))
        settings = get_settings()
        token = create_access_token(
            usuario_id=paciente_id,
            organizacao_id=organizacao_id,
            papel=Role.PACIENTE.value,
            secret_key=self._secret_key or settings.JWT_SECRET_KEY,
            algorithm=self._algorithm or settings.JWT_ALGORITHM,
            expire_minutes=self._access_token_expire_minutes
            or settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        )

        expire_minutes = (
            self._access_token_expire_minutes
            if self._access_token_expire_minutes is not None
            else settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

        return VerificarOtpOutputDTO(
            access_token=token,
            token_type="bearer",  # noqa: S106
            expires_in=expire_minutes * 60,
            paciente_id=paciente_id,
        )
