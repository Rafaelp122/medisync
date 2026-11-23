"""Unit tests for consultation_router: deep PEPService + DocumentoService DI."""

import inspect
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import Role
from src.main import create_app
from src.modules.consultation.application.dtos import (
    DocumentoAssinadoResult,
    HistoricoAtendimentoItemDTO,
    PacienteDocumentoItemDTO,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
    HistoricoAtendimentoReaderPort,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
)
from src.modules.consultation.composition import (
    DocumentoServiceDep,
    PEPServiceDep,
    QueueStoreAtendimentoReaderAdapter,
    get_atendimento_reader,
    get_documento_service,
    get_pep_service,
)
from src.modules.consultation.domain.exceptions import (
    DocumentoClinicoNaoEncontradoError,
)
from src.modules.consultation.presentation.dependencies import (
    require_clinical_mutation_access,
    require_clinical_read_access,
    require_paciente_autenticado,
)
from src.modules.consultation.presentation.routers.consultation_router import (
    consultation_router,
)

from tests.doubles import FakeAsyncSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _make_doctor(user_id: UUID | None = None) -> AuthenticatedUser:
    uid = user_id if user_id is not None else uuid4()
    return AuthenticatedUser(
        usuario_id=uid,
        papel=Role.MEDICO,
        token_id=uuid4(),
        raw_token="fake-jwt-token",
    )


def _make_patient(user_id: UUID | None = None) -> AuthenticatedUser:
    uid = user_id if user_id is not None else uuid4()
    return AuthenticatedUser(
        usuario_id=uid,
        papel=Role.PACIENTE,
        token_id=uuid4(),
        raw_token="fake-patient-jwt",
    )


class FakePEPService:
    """Named fake PEPService for router delegation and IDOR tests."""

    def __init__(
        self,
        *,
        pdf_bytes: bytes = b"%PDF-pep-compiled%",
        compilar_error: Exception | None = None,
        historico: list[HistoricoAtendimentoItemDTO] | None = None,
        documentos: list[PacienteDocumentoItemDTO] | None = None,
        patient_pdf_bytes: bytes = b"%PDF-patient%",
    ) -> None:
        self.pdf_bytes = pdf_bytes
        self.compilar_error = compilar_error
        self.historico = historico or []
        self.documentos = documentos or []
        self.patient_pdf_bytes = patient_pdf_bytes
        self.compilar_calls: list[tuple[UUID, UUID | None]] = []
        self.historico_calls: list[UUID] = []
        self.documentos_calls: list[UUID] = []
        self.patient_pdf_calls: list[tuple[UUID, UUID]] = []

    async def compilar_pdf(
        self, documento_id: UUID, *, atendimento_id: UUID | None = None
    ) -> bytes:
        self.compilar_calls.append((documento_id, atendimento_id))
        if self.compilar_error is not None:
            raise self.compilar_error
        return self.pdf_bytes

    async def listar_historico_paciente(
        self, paciente_id: UUID
    ) -> list[HistoricoAtendimentoItemDTO]:
        self.historico_calls.append(paciente_id)
        return self.historico

    async def listar_documentos_paciente(
        self, paciente_id: UUID
    ) -> list[PacienteDocumentoItemDTO]:
        self.documentos_calls.append(paciente_id)
        return self.documentos

    async def compilar_pdf_para_paciente(
        self, documento_id: UUID, paciente_id: UUID
    ) -> bytes:
        self.patient_pdf_calls.append((documento_id, paciente_id))
        return self.patient_pdf_bytes


class FakeDocumentoService:
    """Named fake DocumentoService for prescription, liveness, and signing routes."""

    def __init__(self, assinar_result: DocumentoAssinadoResult | None = None) -> None:
        self.assinar_result = assinar_result
        self.assinar_calls: list[dict[str, Any]] = []

    async def assinar(
        self,
        documento_id: UUID,
        atendimento_id: UUID,
        credenciais: DoctorCertificateCredentials,
    ) -> DocumentoAssinadoResult:
        self.assinar_calls.append(
            {
                "documento_id": documento_id,
                "atendimento_id": atendimento_id,
                "credenciais": credenciais,
            }
        )
        assert self.assinar_result is not None
        return self.assinar_result


def test_consultation_router_separates_pep_and_documento_services() -> None:
    """Document emission/liveness/sign use DocumentoServiceDep; PEP keeps rest."""
    doc_service_endpoints = {
        "validar_prescricao_medicamento",
        "emitir_documento_clinico",
        "solicitar_desafio_liveness_prescricao",
        "verificar_liveness_prescricao",
        "assinar_documento",
    }

    for route in consultation_router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        sig = inspect.signature(endpoint)
        service_param = sig.parameters.get("service")
        if service_param is None:
            continue
        if endpoint.__name__ in doc_service_endpoints:
            assert service_param.annotation is DocumentoServiceDep, (
                f"{endpoint.__name__} must use DocumentoServiceDep"
            )
        else:
            assert service_param.annotation is PEPServiceDep, (
                f"{endpoint.__name__} must use PEPServiceDep"
            )


@pytest.mark.asyncio
async def test_obter_documento_pdf_route_passes_atendimento_id_for_idor_check() -> None:
    """GET .../pdf passes atendimento_id to PEPService.compilar_pdf (IDOR 404)."""
    app = create_app()
    atend_id = uuid4()
    doc_id = uuid4()
    doctor = _make_doctor()
    fake_pep = FakePEPService(pdf_bytes=b"%PDF-pep-compiled%")

    app.dependency_overrides[get_pep_service] = lambda: fake_pep
    app.dependency_overrides[require_clinical_read_access] = lambda: doctor

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/consultations/{atend_id}/documents/{doc_id}/pdf",
        )

    assert resp.status_code == 200
    assert resp.content == b"%PDF-pep-compiled%"
    assert resp.headers["content-type"] == "application/pdf"
    assert f'filename="{doc_id}.pdf"' in resp.headers["content-disposition"]
    assert fake_pep.compilar_calls == [(doc_id, atend_id)]

    # Cross-attendance IDOR must return HTTP 404
    fake_pep_idor = FakePEPService(
        compilar_error=DocumentoClinicoNaoEncontradoError(
            f"Documento clínico '{doc_id}' não pertence ao atendimento '{atend_id}'."
        )
    )
    app.dependency_overrides[get_pep_service] = lambda: fake_pep_idor
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_404 = await client.get(
            f"/api/v1/consultations/{atend_id}/documents/{doc_id}/pdf",
        )
    assert resp_404.status_code == 404


@pytest.mark.asyncio
async def test_assinar_documento_route_uses_documento_service() -> None:
    """POST .../sign calls DocumentoService.assinar through DocumentoServiceDep."""
    app = create_app()
    atend_id = uuid4()
    doc_id = uuid4()
    doctor = _make_doctor()

    expected_hash = "f" * 64
    now = datetime.now(UTC)
    fake_doc_svc = FakeDocumentoService(
        assinar_result=DocumentoAssinadoResult(
            documento_id=doc_id,
            tipo_documento="RECEITA_SIMPLES",
            sha256_hash=expected_hash,
            assinado_em=now,
            tamanho_bytes=2048,
            status="ASSINADO",
        )
    )

    app.dependency_overrides[get_documento_service] = lambda: fake_doc_svc
    app.dependency_overrides[require_clinical_mutation_access] = lambda: doctor

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/consultations/{atend_id}/documents/{doc_id}/sign",
            json={
                "token": "bearer-psc-tok",
                "provider": "psc-cloud",
                "certificate_alias": "cert-1",
            },
        )

    assert resp.status_code == 200
    data = cast("dict[str, object]", resp.json())
    assert data["documento_id"] == str(doc_id)
    assert data["status"] == "ASSINADO"
    assert data["sha256_hash"] == expected_hash

    assert fake_doc_svc.assinar_calls == [
        {
            "documento_id": doc_id,
            "atendimento_id": atend_id,
            "credenciais": DoctorCertificateCredentials(
                token="bearer-psc-tok",
                provider="psc-cloud",
                certificate_alias="cert-1",
            ),
        }
    ]


@pytest.mark.asyncio
async def test_patient_portal_routes_delegate_to_pep_service() -> None:
    """GET /me/historico, /me/documentos, /me/documents/{id}/pdf delegate via Dep."""
    app = create_app()
    patient = _make_patient()
    atend_id = uuid4()
    doc_id = uuid4()
    now = datetime.now(UTC)

    fake_pep = FakePEPService(
        historico=[
            HistoricoAtendimentoItemDTO(
                atendimento_id=atend_id,
                status="CONCLUIDO",
                prioridade_clinica=3,
                queixa_principal="Dor torácica leve",
                criado_em=now,
                finalizado_em=now,
                medico_id=uuid4(),
                diagnostico_cid10="R07.4",
                conduta_resumo="Acompanhamento ambulatorial",
            )
        ],
        documentos=[
            PacienteDocumentoItemDTO(
                documento_id=doc_id,
                atendimento_id=atend_id,
                tipo_documento="RECEITA_SIMPLES",
                status_assinatura="ASSINADO",
                token_validacao=str(doc_id),
                criado_em=now,
                assinado_em=now,
            )
        ],
        patient_pdf_bytes=b"%PDF-patient%",
    )

    app.dependency_overrides[get_pep_service] = lambda: fake_pep
    app.dependency_overrides[require_paciente_autenticado] = lambda: patient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_hist = await client.get("/api/v1/consultations/me/historico")
        r_docs = await client.get("/api/v1/consultations/me/documentos")
        r_pdf = await client.get(f"/api/v1/consultations/me/documents/{doc_id}/pdf")

    assert r_hist.status_code == 200
    assert r_hist.json()[0]["atendimento_id"] == str(atend_id)
    assert fake_pep.historico_calls == [patient.usuario_id]

    assert r_docs.status_code == 200
    assert r_docs.json()[0]["documento_id"] == str(doc_id)
    assert fake_pep.documentos_calls == [patient.usuario_id]

    assert r_pdf.status_code == 200
    assert r_pdf.content == b"%PDF-patient%"
    assert fake_pep.patient_pdf_calls == [(doc_id, patient.usuario_id)]


def test_get_atendimento_reader_provides_queue_adapter_with_historico_port() -> None:
    """get_atendimento_reader wires QueueStore adapter with Historico port."""
    fake_session = FakeAsyncSession()
    reader = get_atendimento_reader(cast("AsyncSession", fake_session))
    assert isinstance(reader, QueueStoreAtendimentoReaderAdapter)
    assert isinstance(reader, AtendimentoReaderPort)
    assert isinstance(reader, HistoricoAtendimentoReaderPort)
