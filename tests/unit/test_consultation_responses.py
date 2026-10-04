"""Contracts for ADR-008 response schemas and core error mapping (Fase 8)."""

from datetime import UTC, datetime
from uuid import uuid4

from src.core.errors import DomainError, NotFoundError, ValidationError
from src.modules.consultation.application.dtos import (
    DocumentoAssinadoResult,
    DownloadResult,
    ProntuarioResumoDTO,
)
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    DocumentoClinicoNaoEncontradoError,
    EvolucaoNaoEncontradaError,
    PrescricaoFisicaObrigatoriaError,
)
from src.modules.consultation.presentation.schemas import (
    AssinarDocumentoResponse,
    DownloadUrlResponse,
    FinalizarConsultaResponse,
    ProntuarioResponse,
    ValidarPrescricaoResponse,
)


def test_error_hierarchy_status_mapping() -> None:
    presc = PrescricaoFisicaObrigatoriaError("Morfina exige talonário.")
    assert isinstance(presc, ValidationError)
    assert isinstance(presc, DomainError)
    assert presc.status_code == 422
    assert presc.code == "PRESCRICAO_FISICA_OBRIGATORIA"

    fin = ConsultaFinalizadaError("Imutável.")
    assert isinstance(fin, DomainError)
    assert fin.status_code == 409

    evo = EvolucaoNaoEncontradaError("Nenhuma evolução.")
    assert isinstance(evo, NotFoundError)
    assert evo.status_code == 404
    assert evo.code == "EVOLUCAO_NAO_ENCONTRADA"

    doc = DocumentoClinicoNaoEncontradoError("Não encontrado.")
    assert isinstance(doc, NotFoundError)
    assert doc.status_code == 404
    assert doc.code == "DOCUMENTO_CLINICO_NAO_ENCONTRADO"


def test_validar_prescricao_response_payload() -> None:
    resp = ValidarPrescricaoResponse(
        status="PERMITIDO",
        medicamento="Dipirona 500mg",
        mensagem="Substância autorizada para prescrição digital em telemedicina.",
    )
    assert resp.model_dump() == {
        "status": "PERMITIDO",
        "medicamento": "Dipirona 500mg",
        "mensagem": "Substância autorizada para prescrição digital em telemedicina.",
    }


def test_finalizar_consulta_response_payload() -> None:
    atend = uuid4()
    resp = FinalizarConsultaResponse(
        status="FINALIZADO",
        atendimento_id=atend,
        is_finalizado=True,
        mensagem="Consulta finalizada com sucesso. "
        "Registros PEP travados de forma imutável.",
    )
    data = resp.model_dump(mode="json")
    assert data["status"] == "FINALIZADO"
    assert data["atendimento_id"] == str(atend)
    assert data["is_finalizado"] is True


def test_download_url_response_via_dto() -> None:
    doc_id = uuid4()
    dto = DownloadResult(
        documento_id=doc_id,
        download_url="https://s3.local/presigned",
        expires_in_seconds=300,
        chave_s3="orgs/1/consultations/x/documents/y.pdf",
    )
    resp = DownloadUrlResponse.model_validate(dto)
    assert resp.documento_id == doc_id
    assert resp.download_url == "https://s3.local/presigned"
    assert resp.expires_in_seconds == 300


def test_prontuario_response_via_dto() -> None:
    atend = uuid4()
    dto = ProntuarioResumoDTO(
        atendimento_id=atend,
        evolucao=None,
        documentos=[],
        is_finalizado=False,
    )
    resp = ProntuarioResponse.model_validate(dto)
    assert resp.atendimento_id == atend
    assert resp.evolucao is None
    assert resp.documentos == []
    assert resp.is_finalizado is False


def test_assinar_response_via_dto() -> None:
    doc_id = uuid4()
    dto = DocumentoAssinadoResult(
        documento_id=doc_id,
        tipo_documento="RECEITA_SIMPLES",
        sha256_hash="a" * 64,
        assinado_em=datetime.now(UTC),
        tamanho_bytes=1234,
    )
    resp = AssinarDocumentoResponse.model_validate(dto)
    assert resp.documento_id == doc_id
    assert resp.tipo_documento == "RECEITA_SIMPLES"
    assert resp.tamanho_bytes == 1234
    assert resp.status == "ASSINADO"
