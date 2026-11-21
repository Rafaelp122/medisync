"""Auth composition root: concrete adapter wiring for AuthService and patient auth.

Single place in auth module allowed to import infrastructure adapters.
Routers and tests must resolve services via AuthServiceDep/PatientAuthServiceDep.
"""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import SqlAuditTrailAdapter
from src.core.authz.revocation import TokenRevocationPort, get_token_revocation
from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.core.valkey import get_valkey_client
from src.modules.auth.application.ports.active_attendance_lookup_port import (
    ActiveAttendanceLookupPort,
)
from src.modules.auth.application.ports.auth_rate_limiter_port import (
    AuthRateLimiterPort,
)
from src.modules.auth.application.ports.challenge_store_port import (
    ChallengeStorePort,
)
from src.modules.auth.application.ports.identity_reader_port import (
    IdentityReaderPort,
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
from src.modules.auth.application.ports.sms_sender_port import SmsSenderPort
from src.modules.auth.application.ports.token_service_port import TokenServicePort
from src.modules.auth.application.services.auth_service import AuthService
from src.modules.auth.application.services.patient_auth_service import (
    PatientAuthService,
)
from src.modules.auth.application.services.patient_webauthn_service import (
    PatientWebAuthnService,
)
from src.modules.auth.infrastructure.argon2_hasher import Argon2PasswordHasher
from src.modules.auth.infrastructure.fake_sms_adapter import FakeSmsSenderAdapter
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.auth.infrastructure.patient_credential_repository_sql import (
    SqlPatientCredentialRepository,
)
from src.modules.auth.infrastructure.valkey_challenge_store import (
    InMemoryChallengeStore,
    ValkeyChallengeStore,
)
from src.modules.auth.infrastructure.valkey_rate_limiter import (
    FakeAuthRateLimiter,
    ValkeyAuthRateLimiter,
)
from src.modules.identity.composition import (
    build_identity_reader_sql_for_session,
    build_identity_writer_sql_for_session,
)
from src.modules.queue.composition import (
    build_active_attendance_reader_for_session,
)

_sms_adapter_instance = FakeSmsSenderAdapter()
_memory_challenge_store_instance = InMemoryChallengeStore()


def get_sms_sender() -> SmsSenderPort:
    """Provide SMS sender port adapter."""
    return _sms_adapter_instance


SmsSenderDep = Annotated[SmsSenderPort, Depends(get_sms_sender)]


def get_cookie_secure_flag() -> bool | None:
    """Resolve explicit Secure cookie flag for production/staging profiles (ADR-009)."""
    settings = get_settings()
    if settings.ENVIRONMENT in ("production", "staging"):
        return True
    return None


CookieSecureDep = Annotated[bool | None, Depends(get_cookie_secure_flag)]


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


def get_challenge_store(valkey: Redis | None = None) -> ChallengeStorePort:
    """Provide ChallengeStorePort adapter based on Valkey client or active profile."""
    if valkey is not None:
        return ValkeyChallengeStore(client=valkey)
    settings = get_settings()
    if settings.RATE_LIMIT_BACKEND == "memory":
        return _memory_challenge_store_instance
    return ValkeyChallengeStore()


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
    active_attendance_lookup: ActiveAttendanceLookupPort | None = None,
    identity_writer: IdentityWriterPort | None = None,
    credential_repo: PatientCredentialRepositoryPort | None = None,
    password_hasher: PasswordHasherPort | None = None,
    govbr_oidc_enabled: bool | None = None,
    rate_limiter: AuthRateLimiterPort | None = None,
    challenge_store: ChallengeStorePort | None = None,
    token_service: TokenServicePort | None = None,
) -> PatientAuthService:
    """Build PatientAuthService outside request scope (tests/worker tooling)."""
    settings = get_settings()
    reader = identity_reader or build_identity_reader_sql_for_session(session)
    writer = identity_writer or build_identity_writer_sql_for_session(session)
    cred_repo = credential_repo or SqlPatientCredentialRepository(session=session)
    hasher = password_hasher or get_password_hasher()
    sender = sms_sender or get_sms_sender()
    limiter = rate_limiter or get_rate_limiter()
    store = challenge_store or get_challenge_store(valkey=valkey)
    tok_svc = token_service or get_token_service()
    attendance_lookup = (
        active_attendance_lookup or build_active_attendance_reader_for_session(session)
    )
    return PatientAuthService(
        token_service=tok_svc,
        challenge_store=store,
        rate_limiter=limiter,
        identity_reader=reader,
        sms_sender=sender,
        expose_debug_otp=(
            settings.DEBUG and settings.ENVIRONMENT in ("development", "test")
        ),
        active_attendance_lookup=attendance_lookup,
        identity_writer=writer,
        credential_repo=cred_repo,
        password_hasher=hasher,
        govbr_oidc_enabled=(
            settings.GOVBR_OIDC_ENABLED
            if govbr_oidc_enabled is None
            else govbr_oidc_enabled
        ),
        session=session,
    )


def get_patient_auth_service(
    session: DbSessionDep,
    valkey: Annotated[Redis, Depends(get_valkey_client)],
) -> PatientAuthService:
    """Provide PatientAuthService instance wired with dependencies."""
    return build_patient_auth_service_for_session(session=session, valkey=valkey)


PatientAuthServiceDep = Annotated[PatientAuthService, Depends(get_patient_auth_service)]


def build_patient_webauthn_service_for_session(
    session: AsyncSession,
    valkey: Redis | None = None,
    identity_reader: IdentityReaderPort | None = None,
    identity_writer: IdentityWriterPort | None = None,
    active_attendance_lookup: ActiveAttendanceLookupPort | None = None,
    challenge_store: ChallengeStorePort | None = None,
    token_service: TokenServicePort | None = None,
) -> PatientWebAuthnService:
    """Build PatientWebAuthnService outside request scope (tests/tooling)."""
    settings = get_settings()
    reader = identity_reader or build_identity_reader_sql_for_session(session)
    writer = identity_writer or build_identity_writer_sql_for_session(session)
    store = challenge_store or get_challenge_store(valkey=valkey)
    tok_svc = token_service or get_token_service()
    attendance_lookup = (
        active_attendance_lookup or build_active_attendance_reader_for_session(session)
    )
    return PatientWebAuthnService(
        session=session,
        token_service=tok_svc,
        challenge_store=store,
        identity_reader=reader,
        identity_writer=writer,
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        allowed_origins=tuple(settings.WEBAUTHN_ALLOWED_ORIGINS),
        active_attendance_lookup=attendance_lookup,
        audit_trail=SqlAuditTrailAdapter(session),
    )


def get_patient_webauthn_service(
    session: DbSessionDep,
    valkey: Annotated[Redis, Depends(get_valkey_client)],
) -> PatientWebAuthnService:
    """Provide PatientWebAuthnService wired with Valkey, reader/writer and audit."""
    return build_patient_webauthn_service_for_session(session=session, valkey=valkey)


PatientWebAuthnServiceDep = Annotated[
    PatientWebAuthnService, Depends(get_patient_webauthn_service)
]
