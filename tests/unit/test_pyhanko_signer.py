"""Unit tests for PyHanko ICP-Brasil PAdES cloud signer and PSC OAuth2 client."""

import io
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import async_validate_pdf_signature
from src.core.config import get_settings
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
    ICPBrasilSignerPort,
    SignatureMetadataDTO,
)
from src.modules.consultation.application.ports.pdf_generator_port import (
    DocumentoItemPDFDTO,
    DocumentoPDFPayload,
)
from src.modules.consultation.domain.exceptions import AssinaturaDigitalInvalidaError
from src.modules.consultation.infrastructure.pdf_generator import ReportLabPDFGenerator
from src.modules.consultation.infrastructure.pyhanko_signer import (
    CloudPSCOAuth2Client,
    FakeICPBrasilSigner,
    PyHankoSigner,
)


def _build_valid_pdf() -> bytes:
    """Helper to generate a real PDF/A document using ReportLabPDFGenerator."""
    generator = ReportLabPDFGenerator()
    payload = DocumentoPDFPayload(
        documento_id=uuid4(),
        tipo_documento="RECEITA_SIMPLES",
        data_emissao=datetime(2026, 10, 3, 15, 0, tzinfo=UTC),
        organizacao_nome="Clínica São Rafael de Telemedicina",
        medico_nome="Dr. Roberto Carlos",
        medico_crm="123456",
        medico_crm_uf="SP",
        paciente_nome="Maria Joana dos Santos",
        paciente_cpf="111.222.333-44",
        itens=[
            DocumentoItemPDFDTO(
                medicamento="Dipirona Monoidratada",
                dosagem="500 mg/mL",
                posologia="Tomar 30 gotas a cada 6 horas.",
                duracao="3 dias",
            )
        ],
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    return generator.gerar_pdf(payload)


def test_signer_port_conformance() -> None:
    """Validate both Fake and PyHanko signers satisfy ICPBrasilSignerPort protocol."""
    fake_signer = FakeICPBrasilSigner()
    assert isinstance(fake_signer, ICPBrasilSignerPort)

    pyhanko_signer = PyHankoSigner()
    assert isinstance(pyhanko_signer, ICPBrasilSignerPort)


@pytest.mark.asyncio
async def test_fake_icp_brasil_signer_success() -> None:
    """Validate genuine PAdES signature generation and cryptographic validity."""
    pdf_bytes = _build_valid_pdf()
    signer = FakeICPBrasilSigner()
    creds = DoctorCertificateCredentials(
        token="valid-oauth2-psc-token",
        provider="fake",
        certificate_alias="medico-dr-roberto",
    )
    metadata = SignatureMetadataDTO(
        reason="Prescrição eletrônica assinada digitalmente",
        location="São Paulo - SP",
        field_name="Assinatura_Clinica",
    )

    signed_bytes = await signer.assinar_pdf(pdf_bytes, creds, metadata)

    assert signed_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in signed_bytes
    assert b"/ByteRange" in signed_bytes
    assert b"/Contents" in signed_bytes
    # Parse and cryptographically validate signature with PyHanko
    reader = PdfFileReader(io.BytesIO(signed_bytes))
    assert len(reader.embedded_signatures) == 1
    sig = reader.embedded_signatures[0]
    assert sig.field_name.startswith("Assinatura_Clinica")
    status = await async_validate_pdf_signature(sig)
    assert status.intact is True
    assert status.valid is True

    # Validate signer state records
    assert signer.last_credentials == creds
    assert signer.last_metadata == metadata
    assert signer.last_signed_bytes == signed_bytes


@pytest.mark.asyncio
async def test_fake_icp_brasil_signer_rejects_invalid_pdf() -> None:
    """Verify signer rejects invalid binary or empty PDF."""
    signer = FakeICPBrasilSigner()
    creds = DoctorCertificateCredentials(token="token-xyz", provider="fake")

    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="não é um arquivo PDF válido"
    ):
        await signer.assinar_pdf(b"not a real pdf content", creds)

    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="não é um arquivo PDF válido"
    ):
        await signer.assinar_pdf(b"", creds)


@pytest.mark.asyncio
async def test_fake_icp_brasil_signer_rejects_empty_token() -> None:
    """Verify signer requires non-empty physician authorization token."""
    pdf_bytes = _build_valid_pdf()
    signer = FakeICPBrasilSigner()

    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="Token de autorização do médico"
    ):
        await signer.assinar_pdf(
            pdf_bytes, DoctorCertificateCredentials(token="", provider="fake")
        )

    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="Token de autorização do médico"
    ):
        await signer.assinar_pdf(
            pdf_bytes, DoctorCertificateCredentials(token="   ", provider="fake")
        )


def test_cloud_psc_oauth2_client_url_resolution() -> None:
    """Verify correct endpoint resolution for Brazilian trust providers."""
    client = CloudPSCOAuth2Client()
    settings = get_settings()

    assert client.get_provider_base_url(
        "birdid"
    ) == settings.PSC_BIRDID_ENDPOINT.rstrip("/")
    assert client.get_provider_base_url(
        "safeid"
    ) == settings.PSC_SAFEID_ENDPOINT.rstrip("/")
    assert client.get_provider_base_url(
        "vidaas"
    ) == settings.PSC_VIDAAS_ENDPOINT.rstrip("/")

    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="Provedor PSC não suportado"
    ):
        client.get_provider_base_url("unsupported_psc_provider")


@pytest.mark.asyncio
async def test_cloud_psc_oauth2_client_obter_info_credencial() -> None:
    """Test CSC credentials info query with mocked HTTP responses."""
    client = CloudPSCOAuth2Client()

    # Success case (200 OK)
    mock_resp = httpx.Response(
        200,
        json={"credentialID": "alias-1", "key": {"status": "enabled"}},
        request=httpx.Request(
            "POST", "https://psc.birdid.com.br/csc/v1/credentials/info"
        ),
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        info = await client.obter_info_credencial("birdid", "valid-token", "alias-1")
        assert info.get("credentialID") == "alias-1"

    # Expired token case (401 Unauthorized)
    mock_401 = httpx.Response(
        401,
        request=httpx.Request(
            "POST", "https://psc.birdid.com.br/csc/v1/credentials/info"
        ),
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_401
        with pytest.raises(
            AssinaturaDigitalInvalidaError,
            match="Token de autorização do médico expirado",
        ):
            await client.obter_info_credencial("birdid", "expired-token")

    # Network failure case
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(
            AssinaturaDigitalInvalidaError, match="Falha de comunicação"
        ):
            await client.obter_info_credencial("birdid", "some-token")


@pytest.mark.asyncio
async def test_cloud_psc_oauth2_client_assinar_hash() -> None:
    """Test CSC signHash remote signing with mocked HTTP responses."""
    client = CloudPSCOAuth2Client()

    # Success case
    mock_resp = httpx.Response(
        200,
        json={"signatures": ["b64_signature_raw_bytes_value"]},
        request=httpx.Request(
            "POST", "https://psc.birdid.com.br/csc/v1/signatures/signHash"
        ),
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        sig = await client.assinar_hash(
            provider="birdid",
            token="token-xyz",
            credential_id="cred-1",
            hash_b64="c2hhMjU2aGFzaA==",
        )
        assert sig == "b64_signature_raw_bytes_value"

    # Malformed response (missing signatures)
    mock_malformed = httpx.Response(
        200,
        json={"other": "field"},
        request=httpx.Request(
            "POST", "https://psc.birdid.com.br/csc/v1/signatures/signHash"
        ),
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_malformed
        with pytest.raises(
            AssinaturaDigitalInvalidaError, match="Resposta inválida do PSC"
        ):
            await client.assinar_hash(
                provider="birdid",
                token="token-xyz",
                credential_id="cred-1",
                hash_b64="c2hhMjU2aGFzaA==",
            )

    # Access denied (403 Forbidden)
    mock_403 = httpx.Response(
        403,
        request=httpx.Request(
            "POST", "https://psc.birdid.com.br/csc/v1/signatures/signHash"
        ),
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_403
        with pytest.raises(
            AssinaturaDigitalInvalidaError, match="Acesso negado pelo PSC"
        ):
            await client.assinar_hash(
                provider="birdid",
                token="bad-token",
                credential_id="cred-1",
                hash_b64="c2hhMjU2aGFzaA==",
            )


@pytest.mark.asyncio
async def test_pyhanko_signer_delegates_to_fake_for_test_providers() -> None:
    """Verify PyHankoSigner uses in-memory signer when provider is fake or mock."""
    pdf_bytes = _build_valid_pdf()
    signer = PyHankoSigner()

    for prov in ("fake", "mock", "local"):
        creds = DoctorCertificateCredentials(token="tok-123", provider=prov)
        signed = await signer.assinar_pdf(pdf_bytes, creds)
        assert signed.startswith(b"%PDF-")
        assert b"/ByteRange" in signed


@pytest.mark.asyncio
async def test_pyhanko_signer_cloud_provider_flow() -> None:
    """Verify PyHankoSigner coordinates signHash with PSC client for cloud providers."""
    pdf_bytes = _build_valid_pdf()
    mock_psc = AsyncMock(spec=CloudPSCOAuth2Client)
    mock_psc.assinar_hash.return_value = "remote_sig_base64"

    signer = PyHankoSigner(psc_client=mock_psc)
    creds = DoctorCertificateCredentials(
        token="real-doctor-bearer-token",
        provider="birdid",
        certificate_alias="medico_crm_sp_123456",
    )

    signed = await signer.assinar_pdf(pdf_bytes, creds)
    assert signed.startswith(b"%PDF-")
    assert b"/ByteRange" in signed

    mock_psc.assinar_hash.assert_awaited_once()
    call_kwargs: dict[str, Any] = mock_psc.assinar_hash.await_args.kwargs
    assert call_kwargs["provider"] == "birdid"
    assert call_kwargs["token"] == "real-doctor-bearer-token"
    assert call_kwargs["credential_id"] == "medico_crm_sp_123456"


@pytest.mark.asyncio
async def test_pyhanko_signer_validations() -> None:
    """Verify PyHankoSigner validates input parameters before signing."""
    signer = PyHankoSigner()
    creds = DoctorCertificateCredentials(token="tok", provider="fake")

    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="não é um arquivo PDF válido"
    ):
        await signer.assinar_pdf(b"", creds)

    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="não é um arquivo PDF válido"
    ):
        await signer.assinar_pdf(b"plain-text", creds)

    pdf_bytes = _build_valid_pdf()
    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="Token de autorização do médico"
    ):
        await signer.assinar_pdf(
            pdf_bytes, DoctorCertificateCredentials(token="", provider="fake")
        )
