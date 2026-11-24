"""Unit tests for onboarding and dependent presentation schemas."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError as PydanticValidationError
from src.core.uuid7 import uuid7
from src.modules.identity.presentation.schemas import (
    CriarDependenteRequest,
    DependenteResponse,
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
        status="APTO_PARA_CHAMADA",
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


@pytest.mark.parametrize(
    ("input_sexo", "expected_sexo"),
    [
        ("MASCULINO", "M"),
        ("masculino", "M"),
        ("  Masculino  ", "M"),
        ("M", "M"),
        ("m", "M"),
        ("FEMININO", "F"),
        ("feminino", "F"),
        ("  Feminino  ", "F"),
        ("F", "F"),
        ("f", "F"),
    ],
)
def test_fase_2_request_normaliza_sexo_textual(
    input_sexo: str, expected_sexo: str
) -> None:
    req = Fase2Request(
        paciente_id=uuid7(),
        nome_mae="Maria Aparecida",
        sexo_biologico=input_sexo,  # type: ignore[arg-type]
        cep="01310-100",
        logradouro="Avenida Paulista",
        numero="1000",
        bairro="Bela Vista",
        cidade="São Paulo",
        estado="SP",
    )
    assert req.sexo_biologico == expected_sexo


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


def test_fase_1_request_com_nome_social() -> None:
    req = Fase1Request(
        nome_completo="Carlos Drumond",
        nome_social="Carlinhos Drumond",
        data_nascimento=date(1990, 1, 1),
        telefone="11987654321",
        queixa_principal="Febre e tosse",
        tcle_hash=SAMPLE_TCLE_HASH,
        cpf="11144477735",
    )
    assert req.nome_social == "Carlinhos Drumond"


def test_fase_2_request_e_response_com_nome_social() -> None:
    paciente_id = uuid7()
    req = Fase2Request(
        paciente_id=paciente_id,
        nome_social="Carla Silva",
        nome_mae="Maria Silva",
        sexo_biologico="F",
        cep="01310-100",
        logradouro="Av Paulista",
        numero="1000",
        bairro="Bela Vista",
        cidade="São Paulo",
        estado="SP",
    )
    assert req.nome_social == "Carla Silva"

    resp = Fase2Response(
        paciente_id=paciente_id,
        nome_completo="Carlos Silva",
        nome_social="Carla Silva",
        nome_mae="Maria Silva",
        sexo_biologico="F",
        cep="01310100",
        logradouro="Av Paulista",
        numero="1000",
        bairro="Bela Vista",
        cidade="São Paulo",
        estado="SP",
        alergias=[],
        status="DADOS_COMPLETOS",
    )
    assert resp.nome_social == "Carla Silva"


def test_dependente_response_sem_organizacao_id() -> None:
    resp = DependenteResponse(
        id=uuid7(),
        titular_id=uuid7(),
        dependente_id=uuid7(),
        grau_parentesco="FILHO",
        vinculado_em=datetime.now(UTC),
    )
    assert "organizacao_id" not in resp.model_dump()
    assert resp.grau_parentesco == "FILHO"
    assert resp.outorga_tcle is False


def test_criar_dependente_request_com_outorga_tcle() -> None:
    req = CriarDependenteRequest(
        grau_parentesco="FILHO",
        dependente_id=uuid7(),
        outorga_tcle=True,
    )
    assert req.outorga_tcle is True


def test_autenticar_cadsus_request_exige_data_nascimento_e_segundo_fator() -> None:
    from pydantic import ValidationError as PydanticValidationError
    from src.modules.auth.presentation.schemas import AutenticarCadsusRequest

    with pytest.raises(PydanticValidationError):
        AutenticarCadsusRequest.model_validate({"cpf": "11144477735"})

    with pytest.raises(PydanticValidationError, match="nome_mae"):
        AutenticarCadsusRequest(
            cpf="11144477735",
            data_nascimento=date(1990, 5, 15),
        )

    with pytest.raises(PydanticValidationError, match="CPF ou CNS"):
        AutenticarCadsusRequest(data_nascimento=date(1990, 5, 15))

    req_ok = AutenticarCadsusRequest(
        cpf="11144477735",
        data_nascimento=date(1990, 5, 15),
        nome_mae="Maria da Silva",
    )
    assert req_ok.nome_mae == "Maria da Silva"

    req_cns = AutenticarCadsusRequest(
        cpf="11144477735",
        cns="800000000000001",
        data_nascimento=date(1990, 5, 15),
    )
    assert req_cns.cns == "800000000000001"
