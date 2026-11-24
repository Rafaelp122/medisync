"""Brazilian regulatory and clinical document validators (CFM 1.821/2007)."""

import re
import string
from typing import Literal

from src.core.errors import ValidationError
from src.core.privacy import (
    clean_digits,
    mascarar_cpf,
    mascarar_telefone,
    validate_cns,
    validate_cpf,
    validate_telefone,
)

_HEX_DIGITS = frozenset(string.hexdigits)
_VALID_NAME_PATTERN = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ\s'-]+$")


def validate_cep(cep: str) -> str:
    """Validate Brazilian postal code (CEP) 8-digit format."""
    digits = clean_digits(cep)
    if len(digits) != 8:
        msg = (
            f"CEP inválido: deve conter 8 dígitos numéricos; "
            f"recebido '{cep}' com {len(digits)} dígitos."
        )
        raise ValidationError(msg)
    if digits == "00000000":
        raise ValidationError(
            f"CEP inválido: não pode ser composto apenas por zeros ('{cep}')."
        )
    return digits


def validate_nome_mae(nome_mae: str) -> str:
    """Validate mandatory mother's full name under CFM 1.821/2007."""
    clean_name = nome_mae.strip()
    if not clean_name:
        raise ValidationError(
            "Nome da mãe é obrigatório (CFM 1.821/2007); recebido valor vazio."
        )

    if not _VALID_NAME_PATTERN.match(clean_name):
        raise ValidationError(
            "Nome da mãe contém caracteres inválidos. Utilize apenas "
            f"letras e acentos; recebido '{clean_name}'."
        )

    words = clean_name.split()
    if len(words) < 2:
        raise ValidationError(
            "Nome da mãe incompleto: informe o nome completo "
            f"(ao menos dois nomes); recebido apenas '{clean_name}'."
        )

    return clean_name


def validate_tcle_hash(tcle_hash: str) -> str:
    """Validate SHA-256 hash format for digital TCLE consent."""
    clean_hash = tcle_hash.strip().lower()
    if len(clean_hash) != 64:
        raise ValidationError(
            "Hash do TCLE deve conter exatamente 64 caracteres; "
            f"recebido '{clean_hash}' com {len(clean_hash)} caracteres."
        )

    if not all(c in _HEX_DIGITS for c in clean_hash):
        raise ValidationError(
            "Hash do TCLE deve conter apenas caracteres hexadecimais; "
            f"recebido '{clean_hash}'."
        )

    return clean_hash


def validate_sexo_biologico(valor: str) -> Literal["M", "F"]:
    """Valida e normaliza o sexo biológico regulatório para 'M' ou 'F'.

    Regras: CFM 1.821/2007, US-03.
    Documentação: docs/user-stories/US-03-elegibilidade-onboarding-fase2.md
    """
    clean_val = valor.strip().upper()
    if clean_val in ("M", "MASCULINO"):
        return "M"
    if clean_val in ("F", "FEMININO"):
        return "F"
    raise ValidationError(
        f"Sexo biológico '{valor}' inválido: esperados 'M', 'F', "
        "'MASCULINO' ou 'FEMININO'."
    )


__all__ = [
    "clean_digits",
    "mascarar_cpf",
    "mascarar_telefone",
    "validate_cep",
    "validate_cns",
    "validate_cpf",
    "validate_nome_mae",
    "validate_sexo_biologico",
    "validate_tcle_hash",
    "validate_telefone",
]
