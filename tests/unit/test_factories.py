from src.modules.queue.domain.models import Atendimento, StatusAtendimento
from src.modules.triage.domain.models import Triagem

from tests.factories.identity import (
    make_dependente,
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento
from tests.factories.triage import make_triagem


def test_factories_creation() -> None:
    org = make_organizacao()
    assert org.cnpj == "12345678000195"

    prof = make_profissional(org.id or 1)
    assert prof.is_medico() is True

    paciente = make_paciente(org.id or 1)
    assert paciente.cpf == "55566677788"

    dep = make_dependente(org.id or 1)
    assert dep.grau_parentesco == "FILHO"


def test_make_atendimento_factory_defaults() -> None:
    atendimento = make_atendimento(organizacao_id=1)
    assert isinstance(atendimento, Atendimento)
    assert atendimento.id is not None
    assert atendimento.organizacao_id == 1
    assert atendimento.status == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE
    assert atendimento.prioridade_clinica == 5


def test_make_triagem_factory_defaults() -> None:
    triagem = make_triagem(organizacao_id=1)
    assert isinstance(triagem, Triagem)
    assert triagem.id is not None
    assert triagem.organizacao_id == 1
    assert triagem.atendimento_id is not None
    assert triagem.queixa_principal == "Febre alta e calafrios"
    assert triagem.prioridade_calculada == 3
    assert triagem.alerta_samu_disparado is False
