"""Unit tests for clinical audit trail integration in consultation module (ADR-007).

Decisões: docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md
Referência: docs/reference/audit/event-catalog.md
"""

from typing import TYPE_CHECKING, Any, cast

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AtorPapel, AtorTipo
from src.core.uuid7 import uuid7
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
    FinalizarConsultaCommand,
    RegistrarEvolucaoSOAPCommand,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
)
from src.modules.consultation.application.services.documento_service import (
    DocumentoService,
)
from src.modules.consultation.application.services.evolucao_service import (
    EvolucaoService,
)
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.domain.models import DocumentoClinico, EvolucaoClinica
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)

from tests.doubles import (
    FakeAddedResult,
    FakeAsyncSession,
    FakeAuditTrail,
    FakeICPBrasilSigner,
    FakeMemoryStorage,
    FakePDFGenerator,
    FakeResult,
)


@pytest.fixture
def fake_audit_trail() -> FakeAuditTrail:
    return FakeAuditTrail()


@pytest.mark.asyncio
async def test_salvar_evolucao_soap_records_evolucao_audit_event(
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    atend_id = uuid7()
    med_id = uuid7()

    fake_session = FakeAsyncSession([FakeResult(None)])
    svc = EvolucaoService(
        session=cast("AsyncSession", fake_session),
        audit_trail=fake_audit_trail,
    )

    cmd = RegistrarEvolucaoSOAPCommand(
        organizacao_id=org_id,
        atendimento_id=atend_id,
        medico_id=med_id,
        anamnese="Paciente com tosse seca há 3 dias",
        conduta="Prescrito xarope e repouso",
        cid10_principal="J00",
    )

    evolucao = await svc.salvar_evolucao_soap(cmd)
    assert evolucao.cid10_principal == "J00"

    events = fake_audit_trail.get_events_by_type("EVOLUCAO_SOAP_REGISTRADA")
    assert len(events) == 1
    evt = events[0]
    assert evt["organizacao_id"] == org_id
    assert evt["atendimento_id"] == atend_id
    assert evt["ator_tipo"] == AtorTipo.PROFISSIONAL.value
    assert evt["ator_papel"] == AtorPapel.MEDICO.value
    assert evt["ator_id"] == med_id
    assert evt["payload"]["cid10"] == "J00"
    assert evt["payload"]["evolucao_id"] == str(evolucao.id)


@pytest.mark.asyncio
async def test_emitir_documento_records_documento_emitido_audit_event(
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    atend_id = uuid7()
    med_id = uuid7()

    added: list[Any] = []
    fake_session = FakeAsyncSession(
        [FakeResult(None), FakeAddedResult(added)], added=added
    )

    svc = DocumentoService(
        session=cast("AsyncSession", fake_session),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=FakeMemoryStorage(),
        cache=MemorySignedCache(),
        audit_trail=fake_audit_trail,
    )

    cmd = EmitirDocumentoClinicoCommand(
        organizacao_id=org_id,
        atendimento_id=atend_id,
        medico_id=med_id,
        tipo_documento="RECEITA_SIMPLES",
        itens=[
            CriarItemPrescricaoDTO(
                medicamento="Amoxicilina 500mg",
                dosagem="1 cápsula",
                posologia="8 em 8 horas por 7 dias",
            )
        ],
    )

    doc = await svc.emitir_documento(cmd)
    assert doc.tipo_documento == "RECEITA_SIMPLES"

    events = fake_audit_trail.get_events_by_type("DOCUMENTO_CLINICO_EMITIDO")
    assert len(events) == 1
    evt = events[0]
    assert evt["organizacao_id"] == org_id
    assert evt["atendimento_id"] == atend_id
    assert evt["ator_tipo"] == AtorTipo.PROFISSIONAL.value
    assert evt["ator_papel"] == AtorPapel.MEDICO.value
    assert evt["ator_id"] == med_id
    assert evt["payload"]["documento_id"] == str(doc.id)
    assert evt["payload"]["tipo_documento"] == "RECEITA_SIMPLES"
    assert evt["payload"]["itens_qtd"] == 1


@pytest.mark.asyncio
async def test_assinar_documento_records_documento_assinado_audit_event(
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    atend_id = uuid7()
    med_id = uuid7()
    doc_id = uuid7()

    doc = DocumentoClinico(
        id=doc_id,
        organizacao_id=org_id,
        atendimento_id=atend_id,
        medico_id=med_id,
        tipo_documento="RECEITA_SIMPLES",
        chave_s3=f"orgs/{org_id}/consultations/{atend_id}/documents/{doc_id}.pdf",
        sha256_hash="0" * 64,
    )

    fake_session = FakeAsyncSession(
        results=[
            FakeResult(doc),  # query do assinar
            FakeResult(doc),  # query do compilar_pdf
            FakeResult(None),  # query evolucao
            FakeResult(None),  # query organizacao
            FakeResult(None),  # query paciente
            FakeResult(None),  # query medico
        ],
        entities={doc_id: doc},
    )

    storage = FakeMemoryStorage()
    svc = DocumentoService(
        session=cast("AsyncSession", fake_session),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=storage,
        cache=MemorySignedCache(),
        audit_trail=fake_audit_trail,
    )

    creds = DoctorCertificateCredentials(
        token="valid_oauth2_token",
        provider="fake_psc",
    )

    res = await svc.assinar(doc_id, atend_id, creds)
    assert res.documento_id == doc_id

    events = fake_audit_trail.get_events_by_type("DOCUMENTO_CLINICO_ASSINADO")
    assert len(events) == 1
    evt = events[0]
    assert evt["organizacao_id"] == org_id
    assert evt["atendimento_id"] == atend_id
    assert evt["ator_tipo"] == AtorTipo.PROFISSIONAL.value
    assert evt["ator_papel"] == AtorPapel.MEDICO.value
    assert evt["ator_id"] == med_id
    assert evt["payload"]["documento_id"] == str(doc_id)
    assert evt["payload"]["tipo_documento"] == "RECEITA_SIMPLES"
    assert evt["payload"]["sha256_hash"] == res.sha256_hash


@pytest.mark.asyncio
async def test_finalizar_consulta_records_consulta_finalizada_audit_event(
    fake_audit_trail: FakeAuditTrail,
) -> None:
    org_id = 1
    atend_id = uuid7()
    med_id = uuid7()
    evolucao_id = uuid7()

    evolucao = EvolucaoClinica(
        id=evolucao_id,
        organizacao_id=org_id,
        atendimento_id=atend_id,
        medico_id=med_id,
        anamnese="Anamnese teste",
        conduta="Conduta teste",
    )

    fake_session = FakeAsyncSession(
        results=[
            FakeResult(evolucao),  # query evolucao
            FakeResult([]),  # query documentos
        ],
        entities={evolucao_id: evolucao},
    )

    doc_svc = DocumentoService(
        session=cast("AsyncSession", fake_session),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=FakeMemoryStorage(),
        cache=MemorySignedCache(),
    )

    pep_svc = PEPService(
        session=cast("AsyncSession", fake_session),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=FakeMemoryStorage(),
        documento_service=doc_svc,
        audit_trail=fake_audit_trail,
    )

    cmd = FinalizarConsultaCommand(
        organizacao_id=org_id,
        atendimento_id=atend_id,
        medico_id=med_id,
    )

    finalizada = await pep_svc.finalizar_consulta(cmd)
    assert finalizada.is_finalizado is True

    events = fake_audit_trail.get_events_by_type("CONSULTA_FINALIZADA")
    assert len(events) == 1
    evt = events[0]
    assert evt["organizacao_id"] == org_id
    assert evt["atendimento_id"] == atend_id
    assert evt["ator_tipo"] == AtorTipo.PROFISSIONAL.value
    assert evt["ator_papel"] == AtorPapel.MEDICO.value
    assert evt["ator_id"] == med_id
    assert evt["estado_anterior"] == "EM_ATENDIMENTO"
    assert evt["novo_estado"] == "CONCLUIDO"
    assert evt["payload"]["evolucao_id"] == str(evolucao_id)
