"""Macro RBAC roles, permissions, and permission matrix for MediSync Express.

Conforms to OWASP Authorization Cheat Sheet and Architecture Specification
(docs/03-architecture/security-and-authorization.md - Section 4).
"""

from enum import StrEnum


class Role(StrEnum):
    """Corporate and patient roles in MediSync Express."""

    ADMIN_GLOBAL = "ADMIN_GLOBAL"
    GESTOR_UNIDADE = "GESTOR_UNIDADE"
    MEDICO = "MEDICO"
    FATURAMENTO = "FATURAMENTO"
    PACIENTE = "PACIENTE"


class Permission(StrEnum):
    """Fine-grained application permissions."""

    TMA_CONFIG = "tma:config"
    PROFISSIONAL_MANAGE = "profissional:manage"
    QUEUE_VIEW = "queue:view"
    QUEUE_CALL = "queue:call"
    PRONTUARIO_VIEW = "prontuario:view"
    PRONTUARIO_EDIT = "prontuario:edit"
    DOC_SIGN = "doc:sign"
    BILLING_CONSOLIDATE = "billing:consolidate"
    PATIENT_QUEUE_TRACK = "patient:queue_track"
    PATIENT_DOC_VIEW = "patient:doc_view"


# Role-to-Permissions Mapping (Deny by Default / Least Privilege)
# In conformity with CFM 1.821/2007 and 2.314/2022, clinical records (PRONTUARIO_*)
# are strictly restricted to the attending physician (MEDICO).
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.ADMIN_GLOBAL: frozenset(
        {
            Permission.TMA_CONFIG,
            Permission.PROFISSIONAL_MANAGE,
            Permission.QUEUE_VIEW,
            Permission.BILLING_CONSOLIDATE,
        }
    ),
    Role.GESTOR_UNIDADE: frozenset(
        {
            Permission.TMA_CONFIG,
            Permission.PROFISSIONAL_MANAGE,
            Permission.QUEUE_VIEW,
            Permission.BILLING_CONSOLIDATE,
        }
    ),
    Role.MEDICO: frozenset(
        {
            Permission.QUEUE_VIEW,
            Permission.QUEUE_CALL,
            Permission.PRONTUARIO_VIEW,
            Permission.PRONTUARIO_EDIT,
            Permission.DOC_SIGN,
        }
    ),
    Role.FATURAMENTO: frozenset(
        {
            Permission.BILLING_CONSOLIDATE,
        }
    ),
    Role.PACIENTE: frozenset(
        {
            Permission.PATIENT_QUEUE_TRACK,
            Permission.PATIENT_DOC_VIEW,
        }
    ),
}
