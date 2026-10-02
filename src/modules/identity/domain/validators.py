"""Brazilian regulatory and clinical document validators (CFM 1.821/2007)."""

import re
import string

from src.core.errors import ValidationError
from src.modules.identity.domain.models._helpers import clean_digits

_HEX_DIGITS = frozenset(string.hexdigits)
_VALID_NAME_PATTERN = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ\s'-]+$")


def validate_cpf(cpf: str) -> str:
    """Validate Brazilian CPF format and check digits (RFC mod-11)."""
    digits = clean_digits(cpf)
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


def validate_cns(cns: str) -> str:
    """Validate Brazilian Cartão Nacional de Saúde (CNS) 15-digit number."""
    digits = clean_digits(cns)
    if len(digits) != 15:
        raise ValidationError("CNS deve conter exatamente 15 dígitos numéricos.")

    primeiro_digito = digits[0]
    if primeiro_digito not in ("1", "2", "7", "8", "9"):
        raise ValidationError(
            "CNS inválido: deve iniciar com 1, 2, 7, 8 ou 9 conforme padrão DATASUS."
        )

    int_digits = [int(d) for d in digits]

    if primeiro_digito in ("1", "2"):
        # CNS Definitivo
        soma = sum(int_digits[i] * (15 - i) for i in range(11))
        resto = soma % 11
        dv = 0 if resto == 0 else 11 - resto
        if dv == 11:
            dv = 0

        if dv == 10:
            soma_alt = soma + 2
            resto_alt = soma_alt % 11
            dv_alt = 0 if resto_alt == 0 else 11 - resto_alt
            if dv_alt == 11:
                dv_alt = 0
            esperado = [*int_digits[:11], 0, 0, 1, dv_alt]
        else:
            esperado = [*int_digits[:11], 0, 0, 0, dv]

        if int_digits != esperado:
            raise ValidationError("CNS inválido: dígitos verificadores incorretos.")
    else:
        # CNS Provisório (7, 8, 9)
        soma = sum(int_digits[i] * (15 - i) for i in range(15))
        if soma % 11 != 0:
            raise ValidationError("CNS inválido: soma ponderada incorreta.")

    return digits


def validate_cep(cep: str) -> str:
    """Validate Brazilian postal code (CEP) 8-digit format."""
    digits = clean_digits(cep)
    if len(digits) != 8:
        raise ValidationError("CEP inválido: deve conter 8 dígitos numéricos.")
    if digits == "00000000":
        raise ValidationError("CEP inválido: não pode ser composto apenas por zeros.")
    return digits


def validate_telefone(telefone: str) -> str:
    """Validate Brazilian telephone number (10 or 11 digits with DDD)."""
    digits = clean_digits(telefone)
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


def validate_nome_mae(nome_mae: str) -> str:
    """Validate mandatory mother's full name under CFM 1.821/2007."""
    clean_name = nome_mae.strip()
    if not clean_name:
        raise ValidationError("Nome da mãe é obrigatório (CFM 1.821/2007).")

    if not _VALID_NAME_PATTERN.match(clean_name):
        raise ValidationError(
            "Nome da mãe contém caracteres inválidos. Utilize apenas letras e acentos."
        )

    words = clean_name.split()
    if len(words) < 2:
        raise ValidationError(
            "Nome da mãe incompleto: informe o nome completo (ao menos dois nomes)."
        )

    return clean_name


def validate_tcle_hash(tcle_hash: str) -> str:
    """Validate SHA-256 hash format for digital TCLE consent."""
    clean_hash = tcle_hash.strip().lower()
    if len(clean_hash) != 64:
        raise ValidationError("Hash do TCLE deve conter exatamente 64 caracteres.")

    if not all(c in _HEX_DIGITS for c in clean_hash):
        raise ValidationError(
            "Hash do TCLE deve conter apenas caracteres hexadecimais."
        )

    return clean_hash
