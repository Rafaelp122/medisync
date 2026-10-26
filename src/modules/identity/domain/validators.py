"""Brazilian regulatory and clinical document validators (CFM 1.821/2007)."""

import re
import string
from typing import Literal

from src.core.errors import ValidationError
from src.modules.identity.domain.models._helpers import clean_digits

_HEX_DIGITS = frozenset(string.hexdigits)
_VALID_NAME_PATTERN = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ\s'-]+$")


def _mascarar_cpf(cpf: str) -> str:
    digits = clean_digits(cpf)
    if len(digits) >= 11:
        return f"{digits[:3]}.***.***-{digits[-2:]}"
    return f"{digits[:3]}***" if len(digits) >= 3 else "***"


def _mascarar_telefone(tel: str) -> str:
    digits = clean_digits(tel)
    if len(digits) >= 4:
        return f"{digits[:2]}****{digits[-2:]}"
    return "****"


def validate_cpf(cpf: str) -> str:
    """Validate Brazilian CPF format and check digits (RFC mod-11)."""
    digits = clean_digits(cpf)
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


def _validate_cns_definitivo(int_digits: list[int]) -> bool:
    soma = sum(int_digits[i] * (15 - i) for i in range(11))
    resto = soma % 11
    dv = 0 if resto == 0 else 11 - resto
    if dv == 11:
        dv = 0

    if dv == 10:
        resto_alt = (soma + 2) % 11
        dv_alt = 0 if resto_alt == 0 else 11 - resto_alt
        if dv_alt == 11:
            dv_alt = 0
        esperado = [*int_digits[:11], 0, 0, 1, dv_alt]
    else:
        esperado = [*int_digits[:11], 0, 0, 0, dv]

    return int_digits == esperado


def _validate_cns_provisorio(int_digits: list[int]) -> bool:
    soma = sum(int_digits[i] * (15 - i) for i in range(15))
    return soma % 11 == 0


def validate_cns(cns: str) -> str:
    """Validate Brazilian Cartão Nacional de Saúde (CNS) 15-digit number."""
    digits = clean_digits(cns)
    if len(digits) != 15:
        raise ValidationError(
            f"CNS inválido: deve conter exatamente 15 dígitos numéricos "
            f"(recebido '{cns}' com {len(digits)} dígitos)."
        )

    primeiro_digito = digits[0]
    if primeiro_digito not in ("1", "2", "7", "8", "9"):
        raise ValidationError(
            f"CNS inválido: primeiro dígito '{primeiro_digito}' não reconhecido; "
            "esperado iniciar com 1, 2, 7, 8 ou 9 conforme padrão DATASUS."
        )

    int_digits = [int(d) for d in digits]

    if primeiro_digito in ("1", "2"):
        if not _validate_cns_definitivo(int_digits):
            raise ValidationError(
                f"CNS definitivo '{digits}' inválido: dígitos verificadores incorretos."
            )
        return digits

    if not _validate_cns_provisorio(int_digits):
        raise ValidationError(
            f"CNS provisório '{digits}' inválido: soma ponderada incorreta "
            "(esperado múltiplo de 11)."
        )

    return digits


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


def validate_telefone(telefone: str) -> str:
    """Validate Brazilian telephone number (10 or 11 digits with DDD)."""
    digits = clean_digits(telefone)
    if len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]

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


def validate_nome_mae(nome_mae: str) -> str:
    """Validate mandatory mother's full name under CFM 1.821/2007."""
    clean_name = nome_mae.strip()
    if not clean_name:
        raise ValidationError(
            "Nome da mãe é obrigatório (CFM 1.821/2007); recebido valor vazio."
        )

    if not _VALID_NAME_PATTERN.match(clean_name):
        msg = (
            "Nome da mãe contém caracteres inválidos. Utilize apenas "
            f"letras e acentos; recebido '{clean_name}'."
        )
        raise ValidationError(msg)

    words = clean_name.split()
    if len(words) < 2:
        msg = (
            "Nome da mãe incompleto: informe o nome completo "
            f"(ao menos dois nomes); recebido apenas '{clean_name}'."
        )
        raise ValidationError(msg)

    return clean_name


def validate_tcle_hash(tcle_hash: str) -> str:
    """Validate SHA-256 hash format for digital TCLE consent."""
    clean_hash = tcle_hash.strip().lower()
    if len(clean_hash) != 64:
        msg = (
            "Hash do TCLE deve conter exatamente 64 caracteres; "
            f"recebido '{clean_hash}' com {len(clean_hash)} caracteres."
        )
        raise ValidationError(msg)

    if not all(c in _HEX_DIGITS for c in clean_hash):
        msg = (
            "Hash do TCLE deve conter apenas caracteres hexadecimais; "
            f"recebido '{clean_hash}'."
        )
        raise ValidationError(msg)

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
