"""Application ports for triage module."""

from src.modules.triage.application.ports.emergency_notifier import (
    INSTRUCAO_SAMU_PADRAO,
    EmergencyAlertDTO,
    EmergencyNotifierPort,
)

__all__ = [
    "INSTRUCAO_SAMU_PADRAO",
    "EmergencyAlertDTO",
    "EmergencyNotifierPort",
]
