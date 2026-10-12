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
from src.modules.auth.infrastructure.valkey_rate_limiter import ValkeyAuthRateLimiter
from src.modules.auth.infrastructure.valkey_token_revocation import (
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
    """Provide Valkey sliding-window auth rate limiter adapter."""
    return ValkeyAuthRateLimiter()


def get_token_revocation() -> TokenRevocationPort:
    """Provide distributed Valkey token revocation adapter."""
    return ValkeyTokenRevocation()


def get_auth_service(session: DbSessionDep) -> AuthService:
    """Build AuthService with all mandatory ports wired (no infra defaults)."""
    return AuthService(
        session=session,
        hasher=get_password_hasher(),
        token_service=get_token_service(),
        rate_limiter=get_rate_limiter(),
        revocation=get_token_revocation(),
    )


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
    )


def get_patient_auth_service(
    session: DbSessionDep,
    valkey: Annotated[Redis, Depends(get_valkey_client)],
) -> PatientAuthService:
    """Provide PatientAuthService instance wired with dependencies."""
    settings = get_settings()
    return PatientAuthService(
        identity_reader=build_identity_reader_sql_for_session(session),
        valkey_client=valkey,
        sms_sender=get_sms_sender(),
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        access_token_expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    )


PatientAuthServiceDep = Annotated[PatientAuthService, Depends(get_patient_auth_service)]
