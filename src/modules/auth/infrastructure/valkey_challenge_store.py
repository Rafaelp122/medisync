"""Atomic Valkey and in-memory adapters for ChallengeStorePort."""

import contextlib
import hmac
import json
import time
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from redis.asyncio import ConnectionPool, Redis

if TYPE_CHECKING:
    from collections.abc import Sequence

from src.core.errors import ServiceUnavailableError
from src.core.valkey import get_valkey_pool
from src.modules.auth.application.dtos import OtpVerifyOutcomeDTO
from src.modules.auth.application.ports.challenge_store_port import (
    ChallengeStorePort,
)

_OTP_VERIFY_LUA_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then
    return {'not_found', '', 0}
end
local data = cjson.decode(raw)
local attempts = tonumber(data.attempts or 0)
local max_attempts = tonumber(ARGV[2])
if attempts >= max_attempts then
    redis.call('DEL', KEYS[1])
    return {'max_attempts', '', 0}
end
local stored_hash = tostring(data.code_hash or '')
local input_hash = tostring(ARGV[1])
local same_len = (#stored_hash == #input_hash)
local diff = 0
if same_len then
    for i = 1, #stored_hash do
        if string.byte(stored_hash, i) ~= string.byte(input_hash, i) then
            diff = diff + 1
        end
    end
end
if same_len and diff == 0 then
    redis.call('DEL', KEYS[1])
    return {'valid', tostring(data.paciente_id or ''), max_attempts - attempts}
end
local new_attempts = attempts + 1
if new_attempts >= max_attempts then
    redis.call('DEL', KEYS[1])
    return {'max_attempts', '', 0}
end
data.attempts = new_attempts
local pttl = redis.call('PTTL', KEYS[1])
if pttl > 0 then
    redis.call('SET', KEYS[1], cjson.encode(data), 'PX', pttl)
    return {'invalid', '', max_attempts - new_attempts}
end
redis.call('DEL', KEYS[1])
return {'not_found', '', 0}
"""

_VALID_STATUSES: frozenset[str] = frozenset(
    {"valid", "invalid", "not_found", "max_attempts"}
)


def _decode_redis_text(raw: object) -> str:
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode("utf-8")
    return str(raw)


def _decode_lua_outcome(raw_result: object, key: str) -> OtpVerifyOutcomeDTO:
    if not isinstance(raw_result, (list, tuple)):
        raise ServiceUnavailableError(
            "Resposta inesperada do script Lua OTP no Valkey "
            f"(chave='{key}', tipo={type(raw_result).__name__})."
        )
    seq = list(cast("Sequence[object]", raw_result))
    if len(seq) < 3:
        raise ServiceUnavailableError(
            "Resposta incompleta do script Lua OTP no Valkey "
            f"(chave='{key}', tamanho={len(seq)})."
        )
    status = _decode_redis_text(seq[0])
    if status not in _VALID_STATUSES:
        raise ServiceUnavailableError(
            f"Status desconhecido retornado pelo script Lua OTP ('{status}'; "
            f"esperados: {sorted(_VALID_STATUSES)})."
        )
    raw_paciente = _decode_redis_text(seq[1]).strip()
    paciente_id = UUID(raw_paciente) if raw_paciente else None
    remaining = int(str(seq[2]))
    return OtpVerifyOutcomeDTO(
        status=cast(
            'Literal["valid", "invalid", "not_found", "max_attempts"]',
            status,
        ),
        paciente_id=paciente_id,
        tentativas_restantes=max(0, remaining),
    )


async def _close_owned_client(client: Redis | None, owns_client: bool) -> None:
    if owns_client and client is not None:
        with contextlib.suppress(Exception):
            await client.aclose()


class ValkeyChallengeStore(ChallengeStorePort):
    """Fail-closed atomic Valkey store for WebAuthn challenges and OTP verification."""

    def __init__(
        self,
        client: Redis | None = None,
        pool: ConnectionPool | None = None,
    ) -> None:
        self._client = client
        self._pool = pool

    def _acquire_client(self) -> tuple[Redis, bool]:
        if self._client is not None:
            return self._client, False
        active_pool = self._pool if self._pool is not None else get_valkey_pool()
        return Redis(connection_pool=active_pool), True

    async def store_one_time(
        self,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        """Persist short-lived challenge or OTP JSON payload with explicit TTL."""
        client: Redis | None = None
        owns_client = False
        try:
            client, owns_client = self._acquire_client()
            await client.set(key, value, ex=max(1, ttl_seconds))  # pyright: ignore[reportUnknownMemberType]
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            raise ServiceUnavailableError(
                "Armazenamento distribuído de desafios (Valkey) indisponível ao "
                f"salvar chave '{key}' ({type(exc).__name__}: {exc})."
            ) from exc
        finally:
            await _close_owned_client(client, owns_client)

    async def consume_one_time(self, key: str) -> str | None:
        """Atomically fetch and delete challenge via Valkey GETDEL (anti-replay)."""
        client: Redis | None = None
        owns_client = False
        try:
            client, owns_client = self._acquire_client()
            raw: object = await client.getdel(key)  # pyright: ignore[reportUnknownMemberType]
            if raw is None:
                return None
            return _decode_redis_text(raw)
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            raise ServiceUnavailableError(
                "Armazenamento distribuído de desafios (Valkey) indisponível ao "
                f"consumir chave '{key}' ({type(exc).__name__}: {exc})."
            ) from exc
        finally:
            await _close_owned_client(client, owns_client)

    async def verify_and_increment_otp(
        self,
        key: str,
        code_hash: str,
        max_attempts: int,
    ) -> OtpVerifyOutcomeDTO:
        """Atomically verify SHA-256 OTP hash via Lua in Valkey eliminating TOCTOU."""
        client: Redis | None = None
        owns_client = False
        try:
            client, owns_client = self._acquire_client()
            raw_res = cast(
                "object",
                await client.eval(  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType]
                    _OTP_VERIFY_LUA_SCRIPT,
                    1,
                    key,
                    code_hash,
                    str(max_attempts),
                ),
            )
            return _decode_lua_outcome(raw_res, key)
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            raise ServiceUnavailableError(
                "Armazenamento distribuído de OTP (Valkey) indisponível ao validar "
                f"chave '{key}' ({type(exc).__name__}: {exc})."
            ) from exc
        finally:
            await _close_owned_client(client, owns_client)


class InMemoryChallengeStore(ChallengeStorePort):
    """In-memory ChallengeStorePort adapter for RATE_LIMIT_BACKEND=memory."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, float]] = {}

    async def store_one_time(
        self,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        """Store challenge or serialized OTP state with monotonic expiry."""
        self._entries[key] = (value, time.monotonic() + max(1, ttl_seconds))

    async def consume_one_time(self, key: str) -> str | None:
        """Fetch and remove challenge atomically in memory if not expired."""
        entry = self._entries.pop(key, None)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            return None
        return value

    async def verify_and_increment_otp(
        self,
        key: str,
        code_hash: str,
        max_attempts: int,
    ) -> OtpVerifyOutcomeDTO:
        """Validate OTP hash in constant time and update attempts in memory."""
        entry = self._entries.get(key)
        if entry is None:
            return OtpVerifyOutcomeDTO(status="not_found")
        raw_json, expires_at = entry
        if time.monotonic() > expires_at:
            self._entries.pop(key, None)
            return OtpVerifyOutcomeDTO(status="not_found")

        data = cast("dict[str, object]", json.loads(raw_json))
        attempts = int(str(data.get("attempts", 0)))
        if attempts >= max_attempts:
            self._entries.pop(key, None)
            return OtpVerifyOutcomeDTO(status="max_attempts")

        expected_hash = str(data.get("code_hash", ""))
        if hmac.compare_digest(expected_hash, code_hash):
            self._entries.pop(key, None)
            raw_pac = data.get("paciente_id")
            return OtpVerifyOutcomeDTO(
                status="valid",
                paciente_id=UUID(str(raw_pac)) if raw_pac else None,
                tentativas_restantes=max_attempts - attempts,
            )

        new_attempts = attempts + 1
        if new_attempts >= max_attempts:
            self._entries.pop(key, None)
            return OtpVerifyOutcomeDTO(status="max_attempts")

        data["attempts"] = new_attempts
        self._entries[key] = (json.dumps(data), expires_at)
        return OtpVerifyOutcomeDTO(
            status="invalid",
            tentativas_restantes=max_attempts - new_attempts,
        )

    def clear(self) -> None:
        """Reset all stored challenges in memory."""
        self._entries.clear()
