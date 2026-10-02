"""Unit tests for Brazilian identity and CFM regulatory validators."""

import pytest
from src.core.errors import ValidationError
from src.modules.identity.domain.validators import (
    validate_cep,
    validate_cns,
    validate_cpf,
    validate_nome_mae,
    validate_tcle_hash,
    validate_telefone,
)


def test_validate_cpf_valid() -> None:
    # 11144477735 is valid
    assert validate_cpf("111.444.777-35") == "11144477735"
    assert validate_cpf("52998224725") == "52998224725"


def test_validate_cpf_invalid_length_or_digits() -> None:
    with pytest.raises(ValidationError, match="11 dígitos"):
        validate_cpf("12345")

    with pytest.raises(ValidationError, match=r"dígitos iguais|inválido"):
        validate_cpf("111.111.111-11")

    with pytest.raises(ValidationError, match="dígitos verificadores"):
        validate_cpf("111.444.777-99")


def test_validate_cns_valid() -> None:
    # CNS provisório: starts with 7, 8 or 9; sum(digits[i]*(15-i)) % 11 == 0
    # Let's test a valid provisório CNS: 700000000000003
    # 7*15 + 3*1 = 105 + 3 = 108 -> 108 % 11 = 9 != 0.
    # 700000000000005 -> 105 + 5 = 110 -> 110 % 11 = 0!
    valid_cns_prov = "700000000000005"
    assert validate_cns(valid_cns_prov) == "700000000000005"
    assert validate_cns("700.0000.0000.0005") == "700000000000005"


def test_validate_cns_invalid() -> None:
    with pytest.raises(ValidationError, match="15 dígitos"):
        validate_cns("12345")

    with pytest.raises(ValidationError, match="CNS inválido"):
        validate_cns("300000000000000")  # Invalid start digit (3)


def test_validate_cep_valid() -> None:
    assert validate_cep("01310-100") == "01310100"
    assert validate_cep("70040010") == "70040010"


def test_validate_cep_invalid() -> None:
    with pytest.raises(ValidationError, match="8 dígitos"):
        validate_cep("123")

    with pytest.raises(ValidationError, match="inválido"):
        validate_cep("00000-000")


def test_validate_telefone_valid() -> None:
    assert validate_telefone("(11) 98765-4321") == "11987654321"
    assert validate_telefone("2122334455") == "2122334455"


def test_validate_telefone_invalid() -> None:
    with pytest.raises(ValidationError, match=r"DDD|Telefone"):
        validate_telefone("123")

    with pytest.raises(ValidationError, match=r"DDD|Telefone"):
        validate_telefone("01999999999")  # Invalid DDD 01


def test_validate_nome_mae_valid() -> None:
    assert validate_nome_mae("Maria da Silva") == "Maria da Silva"
    assert validate_nome_mae("Ana Paula Souza") == "Ana Paula Souza"


def test_validate_nome_mae_invalid() -> None:
    with pytest.raises(ValidationError, match="nome completo"):
        validate_nome_mae("Maria")  # Single name

    with pytest.raises(ValidationError, match=r"caracteres inválidos|nome completo"):
        validate_nome_mae("Maria 123 Silva")


def test_validate_tcle_hash_valid() -> None:
    valid_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert validate_tcle_hash(valid_hash) == valid_hash


def test_validate_tcle_hash_invalid() -> None:
    with pytest.raises(ValidationError, match="64 caracteres"):
        validate_tcle_hash("invalid-short-hash")

    with pytest.raises(ValidationError, match="hexadecimais"):
        validate_tcle_hash("z" * 64)
