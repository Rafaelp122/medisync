"""Billing domain enumerations."""

from enum import StrEnum


class StatusElegibilidade(StrEnum):
    """Eligibility validation status for health insurance and SUS (RF-02, RN03)."""

    APROVADO = "APROVADO"
    REJEITADO = "REJEITADO"
    TIMEOUT = "TIMEOUT"
    PENDENTE = "PENDENTE"
