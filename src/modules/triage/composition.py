"""Triage module composition root: wiring concrete adapters and services (DI)."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.modules.triage.application.ports.emergency_notifier import (
    EmergencyNotifierPort,
)
from src.modules.triage.application.services.triage_service import TriageService
from src.modules.triage.infrastructure.adapters.samu_emergency_notifier_adapter import (
    SamuEmergencyNotifierAdapter,
)


def get_emergency_notifier() -> EmergencyNotifierPort:
    """Provide emergency notifier adapter for SAMU 192 escape."""
    settings = get_settings()
    return SamuEmergencyNotifierAdapter(webhook_url=settings.SAMU_WEBHOOK_URL)


EmergencyNotifierDep = Annotated[EmergencyNotifierPort, Depends(get_emergency_notifier)]


def build_triage_service_for_session(
    session: AsyncSession,
    notifier: EmergencyNotifierPort | None = None,
) -> TriageService:
    """Build triage service outside request scope (tests/worker tooling)."""
    resolved_notifier = notifier or get_emergency_notifier()
    return TriageService(session=session, emergency_notifier=resolved_notifier)


def get_triage_service(
    session: DbSessionDep,
    notifier: EmergencyNotifierDep,
) -> TriageService:
    """Provide clinical triage evaluation service with DB and SAMU notifier wired."""
    return TriageService(session=session, emergency_notifier=notifier)


TriageServiceDep = Annotated[TriageService, Depends(get_triage_service)]
