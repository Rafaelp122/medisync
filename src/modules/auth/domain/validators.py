"""Validators for patient authentication inputs (phone and CPF)."""

import re

from src.core.errors import ValidationError


def _clean_digits(val: str) -> str:
    """Strip all non-numeric characters from a string."""
    return re.sub(r"\D", "", val)


def validate_cpf(cpf: str) -> str:
    """Validate Brazilian CPF format and check digits (RFC mod-11)."""
    digits = _clean_digits(cpf)
    if len(digits) != 11:
        raise ValidationError("CPF deve conter exatamente 11 dígitos numéricos.")

    if len(set(digits)) == 1:
        raise ValidationError("CPF inválido: sequência com todos os dígitos iguais.")

    int_digits = [int(d) for d in digits]

    # First check digit
    soma_1 = sum(int_digits[i] * (10 - i) for i in range(9))
    resto_1 = soma_1 % 11
    dv_1 = 0 if resto_1 < 2 else 11 - resto_1
    if int_digits[9] != dv_1:
        raise ValidationError("CPF inválido: dígitos verificadores incorretos.")

    # Second check digit
    soma_2 = sum(int_digits[i] * (11 - i) for i in range(10))
    resto_2 = soma_2 % 11
    dv_2 = 0 if resto_2 < 2 else 11 - resto_2
    if int_digits[10] != dv_2:
        raise ValidationError("CPF inválido: dígitos verificadores incorretos.")

    return digits


def validate_telefone(telefone: str) -> str:
    """Validate Brazilian telephone number (10 or 11 digits with DDD)."""
    digits = _clean_digits(telefone)
    if len(digits) not in (10, 11):
        raise ValidationError(
            "Telefone inválido: deve conter DDD e ter 10 ou 11 dígitos numéricos."
        )

    ddd = int(digits[:2])
    if ddd < 11 or ddd > 99:
        raise ValidationError("Telefone inválido: DDD inválido.")

    if len(digits) == 11 and digits[2] != "9":
        raise ValidationError(
            "Telefone celular inválido: nono dígito (9) obrigatório para 11 dígitos."
        )

    return digits


__all__ = ["validate_cpf", "validate_telefone"]
