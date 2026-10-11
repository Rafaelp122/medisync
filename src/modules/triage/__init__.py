"""Triage module root package."""

from src.modules.triage.application.dtos import (
    ResultadoTriagemDTO,
    TriageRiskEvaluationDTO,
)
from src.modules.triage.application.ports.emergency_notifier import (
    EmergencyAlertDTO,
    EmergencyNotifierPort,
)
from src.modules.triage.application.services.triage_service import TriageService

__all__ = [
    "EmergencyAlertDTO",
    "EmergencyNotifierPort",
    "ResultadoTriagemDTO",
    "TriageRiskEvaluationDTO",
    "TriageService",
]
