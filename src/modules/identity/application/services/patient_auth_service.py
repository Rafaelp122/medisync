"""Backward-compatibility re-export for PatientAuthService."""

from src.modules.auth.application.services.patient_auth_service import (  # tach-ignore
    PatientAuthService,
)

__all__ = ["PatientAuthService"]
