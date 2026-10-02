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


def test_make_consultation_factories_defaults() -> None:
    from src.modules.consultation.domain.models import (
        DocumentoClinico,
        DocumentoItem,
        EvolucaoClinica,
        TipoDocumentoClinico,
    )

    from tests.factories.consultation import (
        make_documento_clinico,
        make_documento_item,
        make_evolucao_clinica,
    )

    evolucao = make_evolucao_clinica(organizacao_id=1)
    assert isinstance(evolucao, EvolucaoClinica)
    assert evolucao.id is not None
    assert evolucao.organizacao_id == 1
    assert evolucao.cid10_principal == "J00"

    doc = make_documento_clinico(organizacao_id=1)
    assert isinstance(doc, DocumentoClinico)
    assert doc.id is not None
    assert doc.organizacao_id == 1
    assert doc.tipo_documento == TipoDocumentoClinico.RECEITA_SIMPLES

    item = make_documento_item(organizacao_id=1, documento_id=doc.id)
    assert isinstance(item, DocumentoItem)
    assert item.id is not None
    assert item.organizacao_id == 1
    assert item.medicamento == "Dipirona 500mg"


def test_make_audit_event_factory_defaults() -> None:
    from src.core.audit.models import AtorPapel, AtorTipo, AuditEvent

    from tests.factories.audit import make_audit_event

    evt = make_audit_event(organizacao_id=1)
    assert isinstance(evt, AuditEvent)
    assert evt.id is not None
    assert evt.organizacao_id == 1
    assert evt.atendimento_id is not None
    assert evt.ator_tipo == AtorTipo.PROFISSIONAL
    assert evt.ator_papel == AtorPapel.MEDICO
    assert evt.ator_id is not None
    assert evt.tipo_evento == "STATUS_ATENDIMENTO_ATUALIZADO"
