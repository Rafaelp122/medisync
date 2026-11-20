from typing import TYPE_CHECKING, cast

import pytest
from src.modules.queue.domain.models import Atendimento, StatusAtendimento
from src.modules.triage.domain.models import Triagem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories.identity import (
    make_configuracao_unidade,
    make_dependente,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento
from tests.factories.triage import make_triagem


def test_factories_creation() -> None:
    unidade = make_configuracao_unidade()
    assert unidade.cnpj == "12345678000195"
    assert unidade.singleton_guard is True

    prof = make_profissional()
    assert prof.is_medico() is True

    paciente = make_paciente()
    assert paciente.cpf == "55566677788"

    dep = make_dependente()
    assert dep.grau_parentesco == "FILHO"


def test_make_atendimento_factory_defaults() -> None:
    atendimento = make_atendimento()
    assert isinstance(atendimento, Atendimento)
    assert atendimento.id is not None
    assert not hasattr(atendimento, "organizacao_id")
    assert atendimento.status == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE
    assert atendimento.prioridade_clinica == 5


def test_make_triagem_factory_defaults() -> None:
    triagem = make_triagem()
    assert isinstance(triagem, Triagem)
    assert triagem.id is not None
    assert not hasattr(triagem, "organizacao_id")
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

    evolucao = make_evolucao_clinica()
    assert isinstance(evolucao, EvolucaoClinica)
    assert evolucao.id is not None
    assert not hasattr(evolucao, "organizacao_id")
    assert evolucao.cid10_principal == "J00"

    doc = make_documento_clinico()
    assert isinstance(doc, DocumentoClinico)
    assert doc.id is not None
    assert not hasattr(doc, "organizacao_id")
    assert doc.tipo_documento == TipoDocumentoClinico.RECEITA_SIMPLES

    item = make_documento_item(documento_id=doc.id)
    assert isinstance(item, DocumentoItem)
    assert item.id is not None
    assert not hasattr(item, "organizacao_id")
    assert item.medicamento == "Dipirona 500mg"


def test_make_audit_event_factory_defaults() -> None:
    from src.core.audit.models import AtorPapel, AtorTipo, AuditEvent

    from tests.factories.audit import make_audit_event

    evt = make_audit_event()
    assert isinstance(evt, AuditEvent)
    assert evt.id is not None
    assert not hasattr(evt, "organizacao_id")
    assert evt.atendimento_id is not None
    assert evt.ator_tipo == AtorTipo.PROFISSIONAL
    assert evt.ator_papel == AtorPapel.MEDICO
    assert evt.ator_id is not None
    assert evt.tipo_evento == "STATUS_ATENDIMENTO_ATUALIZADO"


def test_make_auth_factories_defaults() -> None:
    from src.core.authz.roles import Role
    from src.modules.auth.application.dtos import CadastrarCredencialCommand
    from src.modules.auth.domain.models import UsuarioCredencial

    from tests.factories.auth import (
        DEFAULT_TEST_HASH,
        make_cadastrar_credencial_command,
        make_usuario_credencial,
    )

    cred = make_usuario_credencial()
    assert isinstance(cred, UsuarioCredencial)
    assert cred.id is not None
    assert not hasattr(cred, "organizacao_id")
    assert cred.usuario_id is not None
    assert cred.identificador == "dr.plantonista@medisync.local"
    assert cred.senha_hash == DEFAULT_TEST_HASH
    assert cred.papel == Role.MEDICO
    assert cred.ativo is True

    cmd = make_cadastrar_credencial_command()
    assert isinstance(cmd, CadastrarCredencialCommand)
    assert not hasattr(cmd, "organizacao_id")
    assert cmd.usuario_id is not None
    assert cmd.identificador == "dr.plantonista@medisync.local"
    assert cmd.senha_pura == "SenhaForte123!@#"
    assert cmd.papel == Role.MEDICO


def test_clinical_scenario_dataclass() -> None:
    from tests.factories.scenarios import ClinicalScenario

    unidade = make_configuracao_unidade(cnes="2695251")
    pac = make_paciente()
    med = make_profissional()
    atend = make_atendimento(paciente_id=pac.id, medico_id=med.id)

    scenario = ClinicalScenario(
        configuracao_unidade=unidade,
        paciente=pac,
        medico=med,
        atendimento=atend,
    )
    assert scenario.configuracao_unidade == unidade
    assert scenario.paciente == pac
    assert scenario.medico == med
    assert scenario.atendimento == atend


@pytest.mark.asyncio
async def test_seed_clinical_scenario_with_fake_session() -> None:
    from tests.doubles import FakeAsyncSession
    from tests.factories.scenarios import ClinicalScenario, seed_clinical_scenario

    fake_session = FakeAsyncSession()
    scenario = await seed_clinical_scenario(
        cast("AsyncSession", fake_session),
        unidade_cnes="2695251",
    )
    assert isinstance(scenario, ClinicalScenario)
    assert scenario.configuracao_unidade.cnes == "2695251"
    assert not hasattr(scenario.paciente, "organizacao_id")
    assert not hasattr(scenario.medico, "organizacao_id")
    assert not hasattr(scenario.atendimento, "organizacao_id")
    assert fake_session.commits == 3
    assert len(fake_session.added) == 4
