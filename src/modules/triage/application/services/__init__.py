"""Application services for triage module."""

from src.modules.triage.application.dtos import TriageRiskEvaluationDTO
from src.modules.triage.application.services.triage_service import TriageService

__all__ = [
    "TriageRiskEvaluationDTO",
    "TriageService",
]
