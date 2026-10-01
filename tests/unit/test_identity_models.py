from datetime import date
from uuid import uuid4

import pytest
from src.core.errors import ValidationError
from src.modules.identity.domain.models import (
    Dependente,
    Organizacao,
    Paciente,
    Profissional,
)


def test_organizacao_model_attributes_and_defaults():
    org = Organizacao(
        cnpj="12.345.676/0001-90",
        razao_social="Hospital Municipal Santa Clara",
        nome_fantasia="HM Santa Clara",
        modo_publico_sus=True,
        id=42,
    )
    assert org.id == 42
    assert org.cnpj == "12345676000190"  # Sanitize to digits
    assert org.is_sus() is True
    assert org.ativo is True
    assert "tma_estimado_segundos" in org.config_plantao


def test_organizacao_invalid_cnpj_raises_validation_error():
    with pytest.raises(ValidationError, match="CNPJ inválido"):
        Organizacao(
            cnpj="123",  # Invalid length
            razao_social="Clínica Exemplo",
            nome_fantasia="Exemplo",
        )


def test_organizacao_activation_toggle():
    org = Organizacao(
        cnpj="12345678000199",
        razao_social="Posto de Saúde",
        nome_fantasia="Posto",
        ativo=True,
    )
    assert org.ativo is True
    org.desativar()
    assert org.ativo is False
    org.ativar()
    assert org.ativo is True


def test_profissional_medico_requires_crm_and_uf():
    with pytest.raises(ValidationError, match="CRM e UF são obrigatórios"):
        Profissional(
            organizacao_id=1,
            cpf="123.456.789-00",
            nome_completo="Dr. Roberto Silva",
            email="roberto@medisync.com",
            papel="MEDICO",
            crm=None,
            crm_uf=None,
        )


def test_profissional_non_medico_allows_empty_crm():
    prof = Profissional(
        organizacao_id=1,
        cpf="123.456.789-00",
        nome_completo="Gestor Carlos",
        email="carlos@medisync.com",
        papel="GESTOR_UNIDADE",
    )
    assert prof.is_medico() is False
    assert prof.crm is None
    assert prof.crm_uf is None
    prof.desativar()
    assert prof.ativo is False
    prof.ativar()
    assert prof.ativo is True


def test_profissional_invalid_cpf_raises_validation_error():
    with pytest.raises(ValidationError, match="CPF do profissional inválido"):
        Profissional(
            organizacao_id=1,
            cpf="123",  # Invalid length
            nome_completo="Carlos",
            email="carlos@medisync.com",
            papel="GESTOR_UNIDADE",
        )


def test_profissional_model_attributes_and_defaults():
    prof = Profissional(
        organizacao_id=1,
        cpf="12345678900",
        nome_completo="Dra. Paula Souza",
        email="paula@medisync.com",
        papel="MEDICO",
        crm="123456",
        crm_uf="SP",
    )
    assert prof.nome_completo == "Dra. Paula Souza"
    assert prof.email == "paula@medisync.com"
    assert prof.crm == "123456"
    assert prof.crm_uf == "SP"
    assert prof.is_medico() is True
    assert prof.ativo is True


def test_paciente_pediatrico_without_cpf_succeeds_with_cns():
    paciente = Paciente(
        organizacao_id=1,
        cpf=None,
        cns="123456789012345",
        data_nascimento=date.today(),
        nome_completo="Bebê Teste",
        telefone="(11) 98888-7777",
    )
    assert paciente.cpf is None
    assert paciente.cns == "123456789012345"
    assert paciente.is_pediatrico() is True


def test_paciente_adult_with_cpf_succeeds():
    paciente = Paciente(
        organizacao_id=1,
        cpf="123.456.789-01",
        cns=None,
        data_nascimento=date(1990, 5, 20),
        nome_completo="Carlos Silva",
        telefone="11999998888",
    )
    assert paciente.cpf == "12345678901"
    assert paciente.is_pediatrico() is False


def test_paciente_without_cpf_and_without_cns_raises_validation_error():
    with pytest.raises(ValidationError, match="Obrigatório informar CPF ou CNS"):
        Paciente(
            organizacao_id=1,
            cpf=None,
            cns=None,
            data_nascimento=date(2000, 1, 1),
            telefone="11999998888",
        )


def test_paciente_invalid_cpf_length_raises_validation_error():
    with pytest.raises(ValidationError, match="CPF do paciente inválido"):
        Paciente(
            organizacao_id=1,
            cpf="123",
            cns=None,
            data_nascimento=date(2000, 1, 1),
            telefone="11999998888",
        )


def test_paciente_invalid_cns_length_raises_validation_error():
    with pytest.raises(ValidationError, match="CNS inválido"):
        Paciente(
            organizacao_id=1,
            cpf=None,
            cns="12345",
            data_nascimento=date(2000, 1, 1),
            telefone="11999998888",
        )


def test_paciente_alergias_management():
    paciente = Paciente(
        organizacao_id=1,
        cpf="12345678901",
        data_nascimento=date(1995, 1, 1),
        telefone="11999998888",
    )
    assert paciente.alergias == []
    paciente.adicionar_alergia("Dipirona")
    paciente.adicionar_alergia("Penicilina")
    assert paciente.tem_alergia("dipirona") is True
    assert paciente.tem_alergia("Amoxicilina") is False
    paciente.remover_alergia("dipirona")
    assert paciente.tem_alergia("Dipirona") is False


def test_dependente_self_reference_raises_validation_error():
    same_id = uuid4()
    with pytest.raises(
        ValidationError, match="Paciente não pode ser dependente de si mesmo"
    ):
        Dependente(
            organizacao_id=1,
            titular_id=same_id,
            dependente_id=same_id,
            grau_parentesco="FILHO",
        )


def test_dependente_creation_succeeds():
    titular_id = uuid4()
    dep_id = uuid4()
    dep = Dependente(
        organizacao_id=1,
        titular_id=titular_id,
        dependente_id=dep_id,
        grau_parentesco="filho",
    )
    assert dep.titular_id == titular_id
    assert dep.dependente_id == dep_id
    assert dep.grau_parentesco == "FILHO"
