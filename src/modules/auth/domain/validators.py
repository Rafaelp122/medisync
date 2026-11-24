"""Validators for patient authentication inputs (delegating to src.core.privacy)."""

from src.core.privacy import (
    clean_digits,
    mascarar_cpf,
    mascarar_telefone,
    validate_cns,
    validate_cpf,
    validate_telefone,
)

__all__ = [
    "clean_digits",
    "mascarar_cpf",
    "mascarar_telefone",
    "validate_cns",
    "validate_cpf",
    "validate_telefone",
]
