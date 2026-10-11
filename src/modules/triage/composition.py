"""Triage module composition root: wiring concrete adapters and services (DI)."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import DbSessionDep
from src.modules.triage.application.ports.emergency_notifier import (
    EmergencyNotifierPort,
)
from src.modules.triage.application.services.triage_service import TriageService
from src.modules.triage.infrastructure.adapters.samu_emergency_notifier_adapter import (
    SamuEmergencyNotifierAdapter,
)

_emergency_notifier: EmergencyNotifierPort | None = None


def get_emergency_notifier() -> EmergencyNotifierPort:
    """Provide singleton emergency notifier adapter for SAMU 192 escape."""
    global _emergency_notifier
    if _emergency_notifier is None:
        _emergency_notifier = SamuEmergencyNotifierAdapter()
    return _emergency_notifier


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
