"""Unit tests for PyHanko ICP-Brasil PAdES cloud signer and PSC OAuth2 client."""

import io
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import async_validate_pdf_signature
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
    DEFAULT_PSC_ENDPOINTS,
    CloudPSCOAuth2Client,
    FakeICPBrasilSigner,
    PyHankoSigner,
)

from tests.doubles import FakeCloudPSCOAuth2Client


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
    reader = PdfFileReader(io.BytesIO(signed_bytes))
    assert len(reader.embedded_signatures) == 1
    sig = reader.embedded_signatures[0]
    assert sig.field_name.startswith("Assinatura_Clinica")
    status = await async_validate_pdf_signature(sig)
    assert status.intact is True
    assert status.valid is True
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
    """Verify endpoint resolution uses injected mapping without global Settings."""
    default_client = CloudPSCOAuth2Client()
    assert (
        default_client.get_provider_base_url("birdid")
        == DEFAULT_PSC_ENDPOINTS["birdid"]
    )
    assert (
        default_client.get_provider_base_url("safeid")
        == DEFAULT_PSC_ENDPOINTS["safeid"]
    )
    assert (
        default_client.get_provider_base_url("vidaas")
        == DEFAULT_PSC_ENDPOINTS["vidaas"]
    )

    custom_client = CloudPSCOAuth2Client(
        provider_endpoints={"birdid": "https://custom.birdid.local/"}
    )
    assert (
        custom_client.get_provider_base_url("birdid") == "https://custom.birdid.local"
    )

    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="Provedor PSC não suportado"
    ):
        default_client.get_provider_base_url("unsupported_psc_provider")


@pytest.mark.asyncio
async def test_cloud_psc_oauth2_client_obter_info_credencial() -> None:
    """Test CSC credentials info query via MockTransport without patching httpx."""
    ok_client = CloudPSCOAuth2Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={"credentialID": "alias-1", "key": {"status": "enabled"}},
                request=req,
            )
        )
    )
    info = await ok_client.obter_info_credencial("birdid", "valid-token", "alias-1")
    assert info.get("credentialID") == "alias-1"

    unauth_client = CloudPSCOAuth2Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(401, request=req))
    )
    with pytest.raises(
        AssinaturaDigitalInvalidaError,
        match="Token de autorização do médico expirado",
    ):
        await unauth_client.obter_info_credencial("birdid", "expired-token")

    def _raise_connect(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=req)

    net_err_client = CloudPSCOAuth2Client(transport=httpx.MockTransport(_raise_connect))
    with pytest.raises(AssinaturaDigitalInvalidaError, match="Falha de comunicação"):
        await net_err_client.obter_info_credencial("birdid", "some-token")


@pytest.mark.asyncio
async def test_cloud_psc_oauth2_client_assinar_hash() -> None:
    """Test CSC signHash remote signing via MockTransport."""
    list_client = CloudPSCOAuth2Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={"signatures": ["b64_signature_raw_bytes_value"]},
                request=req,
            )
        )
    )
    sig = await list_client.assinar_hash(
        provider="birdid",
        token="token-xyz",
        credential_id="cred-1",
        hash_b64="c2hhMjU2aGFzaA==",
    )
    assert sig == "b64_signature_raw_bytes_value"

    captured_req: list[httpx.Request] = []

    def handle_cms_post(req: httpx.Request) -> httpx.Response:
        captured_req.append(req)
        return httpx.Response(
            200,
            json={"signature": "b64_cms_signature_container_value"},
            request=req,
        )

    cms_client = CloudPSCOAuth2Client(transport=httpx.MockTransport(handle_cms_post))
    sig_cms = await cms_client.assinar_hash(
        provider="birdid",
        token="token-xyz",
        credential_id="cred-1",
        hash_b64="c2hhMjU2aGFzaA==",
        response_format="cms",
    )
    assert sig_cms == "b64_cms_signature_container_value"
    assert len(captured_req) == 1
    sent_body: dict[str, Any] = json.loads(captured_req[0].content)
    assert sent_body.get("responseFormat") == "cms"
    assert sent_body.get("credentialID") == "cred-1"
    assert sent_body.get("hashAlgorithmOID") == "2.16.840.1.101.3.4.2.1"
    assert sent_body.get("signAlgo") == "1.2.840.113549.1.1.1"

    malformed_client = CloudPSCOAuth2Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"other": "field"}, request=req)
        )
    )
    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="Resposta inválida do PSC"
    ):
        await malformed_client.assinar_hash(
            provider="birdid",
            token="token-xyz",
            credential_id="cred-1",
            hash_b64="c2hhMjU2aGFzaA==",
        )

    denied_client = CloudPSCOAuth2Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(403, request=req))
    )
    with pytest.raises(AssinaturaDigitalInvalidaError, match="Acesso negado pelo PSC"):
        await denied_client.assinar_hash(
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
async def test_pyhanko_signer_rejects_fake_when_disallowed() -> None:
    """Verify PyHankoSigner raises when fake provider is disabled."""
    pdf_bytes = _build_valid_pdf()
    signer = PyHankoSigner(allow_fake=False)
    creds = DoctorCertificateCredentials(token="tok-123", provider="fake")

    with pytest.raises(
        AssinaturaDigitalInvalidaError, match="Provedor simulado 'fake' desabilitado"
    ):
        await signer.assinar_pdf(pdf_bytes, creds)


@pytest.mark.asyncio
async def test_pyhanko_signer_cloud_provider_embeds_cms_via_external_signer() -> None:
    """PyHankoSigner embeds genuine Cloud PSC CMS SignedData without Fake fallback."""
    pdf_bytes = _build_valid_pdf()
    fake_psc = FakeCloudPSCOAuth2Client()
    fake_in_memory = FakeICPBrasilSigner()

    signer = PyHankoSigner(
        psc_client=fake_psc,  # pyright: ignore[reportArgumentType]
        fake_signer=fake_in_memory,
        allow_fake=False,
    )
    creds = DoctorCertificateCredentials(
        token="real-doctor-bearer-token",
        provider="birdid",
        certificate_alias="medico_crm_sp_123456",
    )

    signed = await signer.assinar_pdf(pdf_bytes, creds)
    assert signed.startswith(b"%PDF-")
    assert b"/ByteRange" in signed
    assert fake_in_memory.last_signed_bytes is None

    assert len(fake_psc.info_calls) == 1
    assert len(fake_psc.sign_calls) == 1
    assert fake_psc.sign_calls[0]["provider"] == "birdid"
    assert fake_psc.sign_calls[0]["token"] == "real-doctor-bearer-token"
    assert fake_psc.sign_calls[0]["credential_id"] == "medico_crm_sp_123456"
    assert fake_psc.sign_calls[0]["response_format"] == "cms"

    reader = PdfFileReader(io.BytesIO(signed))
    assert len(reader.embedded_signatures) == 1
    status = await async_validate_pdf_signature(reader.embedded_signatures[0])
    assert status.intact is True
    assert status.valid is True


@pytest.mark.asyncio
async def test_pyhanko_signer_cloud_rejeita_cms_invalido_sem_fallback_fake() -> None:
    """Invalid CMS or absent certificate raises AssinaturaDigitalInvalidaError."""
    pdf_bytes = _build_valid_pdf()
    fake_in_memory = FakeICPBrasilSigner()

    bad_cms_psc = FakeCloudPSCOAuth2Client(cms_signature_b64="cmVtb3RlX3NpZ19iYXNlNjQ=")
    signer_prod = PyHankoSigner(
        psc_client=bad_cms_psc,  # pyright: ignore[reportArgumentType]
        fake_signer=fake_in_memory,
        allow_fake=False,
    )
    creds = DoctorCertificateCredentials(token="tok", provider="birdid")
    with pytest.raises(AssinaturaDigitalInvalidaError, match="Container CMS inválido"):
        await signer_prod.assinar_pdf(pdf_bytes, creds)
    assert fake_in_memory.last_signed_bytes is None

    no_cert_psc = FakeCloudPSCOAuth2Client(cert_info={"credentialID": "alias-1"})
    signer_no_cert = PyHankoSigner(
        psc_client=no_cert_psc,  # pyright: ignore[reportArgumentType]
        fake_signer=fake_in_memory,
        allow_fake=True,
    )
    with pytest.raises(AssinaturaDigitalInvalidaError, match="Cadeia de certificados"):
        await signer_no_cert.assinar_pdf(pdf_bytes, creds)
    assert fake_in_memory.last_signed_bytes is None


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
