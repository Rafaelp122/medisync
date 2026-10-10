"""Unit tests for onboarding and dependent presentation schemas."""

from datetime import date
from uuid import UUID

import pytest
from pydantic import ValidationError as PydanticValidationError
from src.core.uuid7 import uuid7
from src.modules.identity.presentation.schemas import (
    CriarDependenteRequest,
    Fase1Request,
    Fase1Response,
    Fase2Request,
    Fase2Response,
)

SAMPLE_TCLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_fase_1_request_valid() -> None:
    req = Fase1Request(
        nome_completo="  Carlos Drumond  ",
        data_nascimento=date(1990, 1, 1),
        telefone=" 11987654321 ",
        queixa_principal="Febre e tosse",
        tcle_hash=SAMPLE_TCLE_HASH,
        cpf="11144477735",
    )
    assert req.nome_completo == "Carlos Drumond"
    assert req.telefone == "11987654321"
    assert req.cpf == "11144477735"


def test_fase_1_request_invalid_hash_or_phone() -> None:
    with pytest.raises(PydanticValidationError):
        Fase1Request(
            nome_completo="Carlos",
            data_nascimento=date(1990, 1, 1),
            telefone="123",  # Too short
            queixa_principal="Febre",
            tcle_hash=SAMPLE_TCLE_HASH,
        )

    with pytest.raises(PydanticValidationError):
        Fase1Request(
            nome_completo="Carlos",
            data_nascimento=date(1990, 1, 1),
            telefone="11987654321",
            queixa_principal="Febre",
            tcle_hash="short-hash",  # Not 64 chars
        )


def test_fase_1_response_serialization() -> None:
    paciente_id = uuid7()
    resp = Fase1Response(
        paciente_id=paciente_id,
        token="token.123",
        status="TRIADO_AGUARDANDO_ELEGIBILIDADE",
        mensagem="Sucesso",
        is_novo_paciente=True,
    )
    data = resp.model_dump()
    assert data["paciente_id"] == paciente_id
    assert data["is_novo_paciente"] is True


def test_fase_2_request_valid() -> None:
    paciente_id = uuid7()
    req = Fase2Request(
        paciente_id=paciente_id,
        nome_mae="  Maria Aparecida da Silva  ",
        sexo_biologico="F",
        cep="01310-100",
        logradouro="Avenida Paulista",
        numero="1000",
        bairro="Bela Vista",
        cidade="São Paulo",
        estado="SP",
        alergias=["Dipirona"],
    )
    assert req.nome_mae == "Maria Aparecida da Silva"
    assert req.sexo_biologico == "F"
    assert req.alergias == ["Dipirona"]
    assert req.token is None

    req_with_token = Fase2Request(
        paciente_id=paciente_id,
        nome_mae="Maria Aparecida da Silva",
        sexo_biologico="F",
        cep="01310-100",
        logradouro="Avenida Paulista",
        numero="1000",
        bairro="Bela Vista",
        cidade="São Paulo",
        estado="SP",
        token="token.hmac123",
    )
    assert req_with_token.token == "token.hmac123"


def test_fase_2_request_invalid_sexo() -> None:
    with pytest.raises(PydanticValidationError):
        Fase2Request(
            paciente_id=uuid7(),
            nome_mae="Maria Aparecida",
            sexo_biologico="X",  # type: ignore[arg-type]
            cep="01310-100",
            logradouro="Avenida Paulista",
            numero="1000",
            bairro="Bela Vista",
            cidade="São Paulo",
            estado="SP",
        )


def test_fase_2_response_serialization() -> None:
    paciente_id = uuid7()
    resp = Fase2Response(
        paciente_id=paciente_id,
        nome_completo="João da Silva",
        nome_mae="Maria da Silva",
        sexo_biologico="M",
        cep="01310100",
        logradouro="Av Paulista",
        numero="1000",
        bairro="Bela Vista",
        cidade="São Paulo",
        estado="SP",
        alergias=["Penicilina"],
        status="DADOS_COMPLETOS",
    )
    assert resp.status == "DADOS_COMPLETOS"


def test_criar_dependente_request_valid() -> None:
    # Linking existing dependent
    req_link = CriarDependenteRequest(
        grau_parentesco="FILHO",
        dependente_id=uuid7(),
    )
    assert req_link.grau_parentesco == "FILHO"
    assert isinstance(req_link.dependente_id, UUID)

    # Creating new dependent
    req_new = CriarDependenteRequest(
        grau_parentesco="FILHA",
        nome_completo="Ana Silva",
        data_nascimento=date(2021, 5, 20),
        cns="700000000000005",
    )
    assert req_new.nome_completo == "Ana Silva"
    assert req_new.dependente_id is None
