"""LGPD pure masking helpers and shared Brazilian document/phone validators."""

import re

from src.core.errors import ValidationError

_PREPOSICOES: frozenset[str] = frozenset({"de", "da", "do", "das", "dos", "e"})


def clean_digits(val: str) -> str:
    """Remove caracteres não numéricos preservando exclusivamente dígitos."""
    return re.sub(r"\D", "", val)


def mascarar_cpf(cpf: str) -> str:
    """Mascara dígitos centrais do CPF em conformidade com privacidade (LGPD Art. 11).

    Exibe exclusivamente os 3 primeiros e 2 últimos dígitos para conferência.
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    digits = clean_digits(cpf)
    if len(digits) != 11:
        return "***.***.***-**"
    return f"{digits[:3]}.***.***-{digits[-2:]}"


def mascarar_cns(cns: str) -> str:
    """Mascara dígitos centrais do CNS em conformidade com privacidade (LGPD Art. 11).

    Exibe os 3 primeiros e 4 últimos dígitos de um CNS de 15 dígitos.
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    digits = clean_digits(cns)
    if len(digits) != 15:
        return "***"
    return f"{digits[:3]}********{digits[-4:]}"


def mascarar_telefone(telefone: str) -> str:
    """Mascara dígitos centrais do telefone conforme LGPD Art. 11.

    Preserva prefixo e sufixo mínimos para rastreabilidade operacional segura.
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    digits = clean_digits(telefone)
    if len(digits) >= 8:
        return f"{digits[:4]}****{digits[-4:]}"
    if len(digits) >= 4:
        return f"{digits[:2]}****{digits[-2:]}"
    return "****"


def _mascarar_token_nome(parte: str) -> str:
    if parte.lower() in _PREPOSICOES:
        return parte.lower()
    if len(parte) <= 1:
        return parte
    return f"{parte[0]}{'*' * (len(parte) - 1)}"


def mascarar_nome(nome: str) -> str:
    """Ofusca prenome e sobrenome preservando iniciais e preposições (LGPD Art. 11).

    Garante minimização de dados identificadores em logs e visualizações operacionais.
    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    partes = nome.strip().split()
    if not partes:
        return "***"
    return " ".join(_mascarar_token_nome(p) for p in partes)


def validate_cpf(cpf: str) -> str:
    """Valida formato e dígitos verificadores de CPF brasileiro (RFC mod-11, LGPD).

    Regras: CFM 1.821/2007, LGPD Art. 11, docs/explanation/domains/identity-domain.md
    """
    digits = clean_digits(cpf)
    masked = mascarar_cpf(cpf)
    if len(digits) != 11:
        raise ValidationError(
            f"CPF deve conter exatamente 11 dígitos numéricos; "
            f"recebido {len(digits)} dígitos ({masked})."
        )

    if len(set(digits)) == 1:
        raise ValidationError(
            f"CPF inválido: sequência com todos os dígitos iguais ({masked})."
        )

    int_digits = [int(d) for d in digits]

    soma_1 = sum(int_digits[i] * (10 - i) for i in range(9))
    resto_1 = soma_1 % 11
    dv_1 = 0 if resto_1 < 2 else 11 - resto_1
    if int_digits[9] != dv_1:
        raise ValidationError(
            f"CPF inválido: dígitos verificadores incorretos ({masked}). "
            f"Esperado primeiro DV '{dv_1}', obtido '{int_digits[9]}'."
        )

    soma_2 = sum(int_digits[i] * (11 - i) for i in range(10))
    resto_2 = soma_2 % 11
    dv_2 = 0 if resto_2 < 2 else 11 - resto_2
    if int_digits[10] != dv_2:
        raise ValidationError(
            f"CPF inválido: dígitos verificadores incorretos ({masked}). "
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
    """Valida dígito verificador de Cartão Nacional de Saúde com 15 dígitos (DATASUS).

    Regras: CFM 1.821/2007, LGPD Art. 11, docs/explanation/domains/identity-domain.md
    """
    digits = clean_digits(cns)
    masked = mascarar_cns(digits if len(digits) == 15 else cns)
    if len(digits) != 15:
        raise ValidationError(
            f"CNS inválido: deve conter exatamente 15 dígitos numéricos "
            f"(recebido '{masked}' com {len(digits)} dígitos)."
        )

    primeiro_digito = digits[0]
    if primeiro_digito not in ("1", "2", "7", "8", "9"):
        raise ValidationError(
            f"CNS inválido: primeiro dígito '{primeiro_digito}' de '{masked}' "
            "não reconhecido; esperado iniciar com 1, 2, 7, 8 ou 9 conforme DATASUS."
        )

    int_digits = [int(d) for d in digits]

    if primeiro_digito in ("1", "2"):
        if not _validate_cns_definitivo(int_digits):
            raise ValidationError(
                f"CNS definitivo '{masked}' inválido: dígitos verificadores incorretos."
            )
        return digits

    if not _validate_cns_provisorio(int_digits):
        raise ValidationError(
            f"CNS provisório '{masked}' inválido: soma ponderada incorreta "
            "(esperado múltiplo de 11)."
        )

    return digits


def validate_telefone(telefone: str) -> str:
    """Valida telefone brasileiro (10 ou 11 dígitos com DDD) com mascaramento LGPD.

    Regras: RN-AUT-03, LGPD Art. 11, docs/explanation/domains/auth-domain.md
    """
    digits = clean_digits(telefone)
    if len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]

    masked = mascarar_telefone(digits or telefone)
    if len(digits) not in (10, 11):
        raise ValidationError(
            f"Telefone inválido: deve conter DDD e ter 10 ou 11 dígitos numéricos; "
            f"recebido {len(digits)} dígitos ({masked})."
        )

    ddd = int(digits[:2])
    if ddd < 11 or ddd > 99:
        raise ValidationError(
            f"Telefone inválido ({masked}): DDD '{ddd}' "
            "fora da faixa permitida (11 a 99)."
        )

    if len(digits) == 11 and digits[2] != "9":
        raise ValidationError(
            f"Telefone celular inválido ({masked}): nono dígito (9) obrigatório "
            f"para 11 dígitos; recebido '{digits[2]}'."
        )

    return digits
