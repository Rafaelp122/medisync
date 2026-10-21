"""Append-only audit trail package for CFM and LGPD compliance (ADR-007)."""

from src.core.audit.adapter import SqlAuditTrailAdapter
from src.core.audit.exceptions import (
    AuditoriaImutavelError,
    AuditoriaInvalidaError,
)
from src.core.audit.models import (
    AtorPapel,
    AtorTipo,
    AuditEvent,
    impedir_delete_audit_event,
    impedir_update_audit_event,
)
from src.core.audit.ports import AuditTrailPort
from src.core.audit.service import AuditService

__all__ = [
    "AtorPapel",
    "AtorTipo",
    "AuditEvent",
    "AuditService",
    "AuditTrailPort",
    "AuditoriaImutavelError",
    "AuditoriaInvalidaError",
    "SqlAuditTrailAdapter",
    "impedir_delete_audit_event",
    "impedir_update_audit_event",
]
