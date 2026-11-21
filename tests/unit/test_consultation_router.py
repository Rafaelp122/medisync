"""Unit tests for consultation_router: single PEPServiceDep injection and routes."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import Role
from src.main import create_app
from src.modules.consultation.application.dtos import DocumentoAssinadoResult
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
    HistoricoAtendimentoReaderPort,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
)
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.composition import (
    QueueStoreAtendimentoReaderAdapter,
    get_atendimento_reader,
    get_pep_service,
)
from src.modules.consultation.presentation.dependencies import (
    require_clinical_mutation_access,
    require_clinical_read_access,
    require_paciente_autenticado,
)
from src.modules.consultation.presentation.routers.consultation_router import (
    consultation_router,
)


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


def test_consultation_router_only_depends_on_pep_service() -> None:
    """Architectural check: consultation_router must not have DocumentoServiceDep."""
    import inspect

    from src.modules.consultation.composition import (
        DocumentoServiceDep,
        get_documento_service,
    )

    for route in consultation_router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        sig = inspect.signature(endpoint)
        for param in sig.parameters.values():
            assert param.annotation is not DocumentoServiceDep, (
                f"{endpoint.__name__} must not use DocumentoServiceDep"
            )
            default = param.default
            if hasattr(default, "dependency"):
                assert default.dependency is not get_documento_service, (
                    f"{endpoint.__name__} must not depend on get_documento_service"
                )


@pytest.mark.asyncio
async def test_obter_documento_pdf_route_uses_pep_service() -> None:
    """GET .../pdf calls PEPService.compilar_pdf through PEPServiceDep."""
    app = create_app()
    atend_id = uuid4()
    doc_id = uuid4()
    doctor = _make_doctor()

    mock_pep = MagicMock(spec=PEPService)
    mock_pep.compilar_pdf = AsyncMock(return_value=b"%PDF-pep-compiled%")

    app.dependency_overrides[get_pep_service] = lambda: mock_pep
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
    mock_pep.compilar_pdf.assert_awaited_once_with(doc_id)


@pytest.mark.asyncio
async def test_assinar_documento_route_uses_pep_service() -> None:
    """POST .../sign calls PEPService.assinar_documento through PEPServiceDep."""
    app = create_app()
    atend_id = uuid4()
    doc_id = uuid4()
    doctor = _make_doctor()

    expected_hash = "f" * 64
    now = datetime.now(UTC)
    mock_pep = MagicMock(spec=PEPService)
    mock_pep.assinar_documento = AsyncMock(
        return_value=DocumentoAssinadoResult(
            documento_id=doc_id,
            tipo_documento="RECEITA_SIMPLES",
            sha256_hash=expected_hash,
            assinado_em=now,
            tamanho_bytes=2048,
            status="ASSINADO",
        )
    )

    app.dependency_overrides[get_pep_service] = lambda: mock_pep
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

    mock_pep.assinar_documento.assert_awaited_once_with(
        documento_id=doc_id,
        atendimento_id=atend_id,
        credenciais=DoctorCertificateCredentials(
            token="bearer-psc-tok",
            provider="psc-cloud",
            certificate_alias="cert-1",
        ),
    )


@pytest.mark.asyncio
async def test_patient_portal_routes_delegate_to_pep_service() -> None:
    """GET /me/historico, /me/documentos, /me/documents/{id}/pdf delegate via Dep."""
    from src.modules.consultation.application.dtos import (
        HistoricoAtendimentoItemDTO,
        PacienteDocumentoItemDTO,
    )

    app = create_app()
    patient = _make_patient()
    atend_id = uuid4()
    doc_id = uuid4()
    now = datetime.now(UTC)

    mock_pep = MagicMock(spec=PEPService)
    mock_pep.listar_historico_paciente = AsyncMock(
        return_value=[
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
        ]
    )
    mock_pep.listar_documentos_paciente = AsyncMock(
        return_value=[
            PacienteDocumentoItemDTO(
                documento_id=doc_id,
                atendimento_id=atend_id,
                tipo_documento="RECEITA_SIMPLES",
                status_assinatura="ASSINADO",
                token_validacao=str(doc_id),
                criado_em=now,
                assinado_em=now,
            )
        ]
    )
    mock_pep.compilar_pdf_para_paciente = AsyncMock(return_value=b"%PDF-patient%")

    app.dependency_overrides[get_pep_service] = lambda: mock_pep
    app.dependency_overrides[require_paciente_autenticado] = lambda: patient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_hist = await client.get("/api/v1/consultations/me/historico")
        r_docs = await client.get("/api/v1/consultations/me/documentos")
        r_pdf = await client.get(f"/api/v1/consultations/me/documents/{doc_id}/pdf")

    assert r_hist.status_code == 200
    assert r_hist.json()[0]["atendimento_id"] == str(atend_id)
    mock_pep.listar_historico_paciente.assert_awaited_once_with(
        paciente_id=patient.usuario_id,
    )

    assert r_docs.status_code == 200
    assert r_docs.json()[0]["documento_id"] == str(doc_id)
    mock_pep.listar_documentos_paciente.assert_awaited_once_with(
        paciente_id=patient.usuario_id,
    )

    assert r_pdf.status_code == 200
    assert r_pdf.content == b"%PDF-patient%"
    mock_pep.compilar_pdf_para_paciente.assert_awaited_once_with(
        documento_id=doc_id,
        paciente_id=patient.usuario_id,
    )


def test_get_atendimento_reader_provides_queue_adapter_with_historico_port() -> None:
    """get_atendimento_reader wires QueueStore adapter with Historico port."""
    from sqlalchemy.ext.asyncio import AsyncSession

    mock_session = MagicMock(spec=AsyncSession)
    reader = get_atendimento_reader(mock_session)
    assert isinstance(reader, QueueStoreAtendimentoReaderAdapter)
    assert isinstance(reader, AtendimentoReaderPort)
    assert isinstance(reader, HistoricoAtendimentoReaderPort)
