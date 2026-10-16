"""Auth composition root: concrete adapter wiring for AuthService (DI Fase 3).

Single place in auth module allowed to import infrastructure adapters.
Routers and tests must resolve AuthService via get_auth_service/AuthServiceDep.
"""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.core.valkey import get_valkey_client
from src.modules.auth.application.ports.auth_rate_limiter_port import (
    AuthRateLimiterPort,
)
from src.modules.auth.application.ports.password_hasher_port import (
    PasswordHasherPort,
)
from src.modules.auth.application.ports.token_revocation_port import (
    TokenRevocationPort,
)
from src.modules.auth.application.ports.token_service_port import TokenServicePort
from src.modules.auth.application.services.auth_service import AuthService
from src.modules.auth.application.services.patient_auth_service import (
    PatientAuthService,
)
from src.modules.auth.infrastructure.argon2_hasher import Argon2PasswordHasher
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.auth.infrastructure.valkey_rate_limiter import (
    FakeAuthRateLimiter,
    ValkeyAuthRateLimiter,
)
from src.modules.auth.infrastructure.valkey_token_revocation import (
    MemoryTokenRevocation,
    ValkeyTokenRevocation,
)
from src.modules.identity.application.ports.identity_reader_port import (
    IdentityReaderPort,
)
from src.modules.identity.application.ports.sms_sender_port import SmsSenderPort
from src.modules.identity.composition import (
    build_identity_reader_sql_for_session,
    get_sms_sender,
)


def get_password_hasher() -> PasswordHasherPort:
    """Provide Argon2id password hasher adapter."""
    return Argon2PasswordHasher()


def get_token_service() -> TokenServicePort:
    """Provide JWT token service adapter bound to current settings."""
    settings = get_settings()
    return JWTTokenService(
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        access_token_expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        refresh_token_expire_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    )


def get_rate_limiter() -> AuthRateLimiterPort:
    """Provide auth rate limiter adapter based on active settings."""
    settings = get_settings()
    if settings.RATE_LIMIT_BACKEND == "memory":
        return FakeAuthRateLimiter()
    return ValkeyAuthRateLimiter()


def get_token_revocation() -> TokenRevocationPort:
    """Provide token revocation adapter based on active settings."""
    settings = get_settings()
    if settings.TOKEN_REVOCATION_BACKEND == "memory":  # noqa: S105
        return MemoryTokenRevocation()
    return ValkeyTokenRevocation()


def build_auth_service_for_session(
    session: AsyncSession,
    hasher: PasswordHasherPort | None = None,
    token_service: TokenServicePort | None = None,
    rate_limiter: AuthRateLimiterPort | None = None,
    revocation: TokenRevocationPort | None = None,
) -> AuthService:
    """Build AuthService outside request scope (tests/worker tooling)."""
    settings = get_settings()
    return AuthService(
        session=session,
        hasher=hasher or get_password_hasher(),
        token_service=token_service or get_token_service(),
        rate_limiter=rate_limiter or get_rate_limiter(),
        revocation=revocation or get_token_revocation(),
        max_attempts=settings.AUTH_RATE_LIMIT_MAX_ATTEMPTS,
        window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )


def get_auth_service(session: DbSessionDep) -> AuthService:
    """Build AuthService with all mandatory ports wired (no infra defaults)."""
    return build_auth_service_for_session(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def build_patient_auth_service_for_session(
    session: AsyncSession,
    valkey: Redis | None = None,
    sms_sender: SmsSenderPort | None = None,
    identity_reader: IdentityReaderPort | None = None,
) -> PatientAuthService:
    """Build PatientAuthService outside request scope (tests/worker tooling)."""
    settings = get_settings()
    reader = identity_reader or build_identity_reader_sql_for_session(session)
    sender = sms_sender or get_sms_sender()
    return PatientAuthService(
        identity_reader=reader,
        valkey_client=valkey,
        sms_sender=sender,
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        access_token_expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        is_debug=settings.DEBUG,
    )


def get_patient_auth_service(
    session: DbSessionDep,
    valkey: Annotated[Redis, Depends(get_valkey_client)],
) -> PatientAuthService:
    """Provide PatientAuthService instance wired with dependencies."""
    return build_patient_auth_service_for_session(session=session, valkey=valkey)


PatientAuthServiceDep = Annotated[PatientAuthService, Depends(get_patient_auth_service)]
