"""Port interface for atomic one-time challenge and OTP storage."""

from typing import Protocol, runtime_checkable

from src.modules.auth.application.dtos import OtpVerifyOutcomeDTO


@runtime_checkable
class ChallengeStorePort(Protocol):
    """Port for atomic one-time challenges (WebAuthn) and OTP verification state."""

    async def store_one_time(
        self,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        """Persist a short-lived challenge or serialized OTP payload with TTL."""
        ...

    async def consume_one_time(self, key: str) -> str | None:
        """Atomically fetch and delete a one-time challenge (GETDEL semantics)."""
        ...

    async def verify_and_increment_otp(
        self,
        key: str,
        code_hash: str,
        max_attempts: int,
    ) -> OtpVerifyOutcomeDTO:
        """Atomically compare OTP hash, delete or increment attempts."""
        ...


__all__ = ["ChallengeStorePort"]
