"""Application services for triage module."""

from src.modules.triage.application.dtos import ResultadoTriagemDTO
from src.modules.triage.application.services.triage_service import TriageService

__all__ = [
    "ResultadoTriagemDTO",
    "TriageService",
]
