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
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
)
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.composition import get_pep_service
from src.modules.consultation.presentation.dependencies import (
    require_clinical_mutation_access,
    require_clinical_read_access,
)
from src.modules.consultation.presentation.routers.consultation_router import (
    consultation_router,
)


def _make_doctor(user_id: UUID | None = None, org_id: int = 1) -> AuthenticatedUser:
    uid = user_id if user_id is not None else uuid4()
    return AuthenticatedUser(
        usuario_id=uid,
        organizacao_id=org_id,
        papel=Role.MEDICO,
        token_id=uuid4(),
        raw_token="fake-jwt-token",
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
            headers={"X-Tenant-ID": "1"},
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
            headers={"X-Tenant-ID": "1"},
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
