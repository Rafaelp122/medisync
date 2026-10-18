"""Validators for patient authentication inputs (phone and CPF)."""

import re

from src.core.errors import ValidationError


def _clean_digits(val: str) -> str:
    """Strip all non-numeric characters from a string."""
    return re.sub(r"\D", "", val)


def _mascarar_cpf(cpf: str) -> str:
    digits = _clean_digits(cpf)
    if len(digits) >= 11:
        return f"{digits[:3]}.***.***-{digits[-2:]}"
    return f"{digits[:3]}***" if len(digits) >= 3 else "***"


def _mascarar_telefone(tel: str) -> str:
    digits = _clean_digits(tel)
    if len(digits) >= 4:
        return f"{digits[:2]}****{digits[-2:]}"
    return "****"


def validate_cpf(cpf: str) -> str:
    """Validate Brazilian CPF format and check digits (RFC mod-11)."""
    digits = _clean_digits(cpf)
    if len(digits) != 11:
        msg = (
            f"CPF deve conter exatamente 11 dígitos numéricos; "
            f"recebido {len(digits)} dígitos ({_mascarar_cpf(cpf)})."
        )
        raise ValidationError(msg)

    if len(set(digits)) == 1:
        masked = _mascarar_cpf(cpf)
        raise ValidationError(
            f"CPF inválido: sequência com todos os dígitos iguais ({masked})."
        )

    int_digits = [int(d) for d in digits]

    # First check digit
    soma_1 = sum(int_digits[i] * (10 - i) for i in range(9))
    resto_1 = soma_1 % 11
    dv_1 = 0 if resto_1 < 2 else 11 - resto_1
    if int_digits[9] != dv_1:
        raise ValidationError(
            f"CPF inválido: dígitos verificadores incorretos ({_mascarar_cpf(cpf)}). "
            f"Esperado primeiro DV '{dv_1}', obtido '{int_digits[9]}'."
        )

    # Second check digit
    soma_2 = sum(int_digits[i] * (11 - i) for i in range(10))
    resto_2 = soma_2 % 11
    dv_2 = 0 if resto_2 < 2 else 11 - resto_2
    if int_digits[10] != dv_2:
        raise ValidationError(
            f"CPF inválido: dígitos verificadores incorretos ({_mascarar_cpf(cpf)}). "
            f"Esperado segundo DV '{dv_2}', obtido '{int_digits[10]}'."
        )

    return digits


def validate_telefone(telefone: str) -> str:
    """Validate Brazilian telephone number (10 or 11 digits with DDD)."""
    digits = _clean_digits(telefone)
    if len(digits) not in (10, 11):
        raise ValidationError(
            f"Telefone inválido: deve conter DDD e ter 10 ou 11 dígitos numéricos; "
            f"recebido {len(digits)} dígitos ({_mascarar_telefone(telefone)})."
        )

    ddd = int(digits[:2])
    if ddd < 11 or ddd > 99:
        raise ValidationError(
            f"Telefone inválido: DDD '{ddd}' fora da faixa permitida (11 a 99)."
        )

    if len(digits) == 11 and digits[2] != "9":
        msg = (
            "Telefone celular inválido: nono dígito (9) obrigatório "
            f"para 11 dígitos; recebido '{digits[2]}'."
        )
        raise ValidationError(msg)

    return digits


__all__ = ["validate_cpf", "validate_telefone"]
