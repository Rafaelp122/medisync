"""PyHanko ICP-Brasil PAdES cloud digital signer and PSC OAuth2 client."""

import base64
import binascii
import io
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import httpx
from asn1crypto import cms as asn1_cms
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.keys.pemder import (
    load_certs_from_pemder_data,
    load_private_key_from_pemder_data,
)
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.signers.pdf_signer import PdfTBSDocument
from pyhanko_certvalidator.registry import SimpleCertificateStore

from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
    ICPBrasilSignerPort,
    SignatureMetadataDTO,
)
from src.modules.consultation.domain.exceptions import (
    AssinaturaDigitalInvalidaError,
)

DEFAULT_PSC_ENDPOINTS: dict[str, str] = {
    "birdid": "https://api.birdid.com.br",
    "safeid": "https://api.safeid.com.br",
    "vidaas": "https://api.vidaas.com.br",
}
_CLOUD_CMS_RESERVED_BYTES = 16384


def _validar_entrada_assinatura(
    pdf_bytes: bytes,
    credenciais: DoctorCertificateCredentials,
) -> None:
    """Validate minimal PDF structure and physician authorization token."""
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
        raise AssinaturaDigitalInvalidaError(
            "Conteúdo fornecido não é um arquivo PDF válido."
        )
    if not credenciais.token or not credenciais.token.strip():
        raise AssinaturaDigitalInvalidaError(
            "Token de autorização do médico não pode ser vazio."
        )


def _decodificar_certificado(raw_cert: object, provider: str) -> asn1_x509.Certificate:
    """Parse a base64 DER or PEM X.509 certificate from PSC response."""
    if not isinstance(raw_cert, str) or not raw_cert.strip():
        raise AssinaturaDigitalInvalidaError(
            f"Certificado vazio ou inválido retornado pelo PSC '{provider}'."
        )
    cleaned = raw_cert.strip()
    if "-----BEGIN CERTIFICATE-----" in cleaned:
        pem_iter = cast(
            "list[asn1_x509.Certificate]",
            list(load_certs_from_pemder_data(cleaned.encode("ascii"))),  # pyright: ignore[reportUnknownArgumentType]
        )
        if not pem_iter:
            raise AssinaturaDigitalInvalidaError(
                f"PEM de certificado sem conteúdo retornado pelo PSC '{provider}'."
            )
        return pem_iter[0]
    try:
        der_bytes = base64.b64decode(cleaned, validate=True)
        return cast("asn1_x509.Certificate", asn1_x509.Certificate.load(der_bytes))  # pyright: ignore[reportUnknownMemberType]
    except (binascii.Error, ValueError) as err:
        raise AssinaturaDigitalInvalidaError(
            f"Certificado X.509 malformado retornado pelo PSC '{provider}': {err}"
        ) from err


def _carregar_certificados_psc(
    cert_info: dict[str, Any],
    provider: str,
) -> tuple[asn1_x509.Certificate, SimpleCertificateStore]:
    """Extract leaf certificate and chain store from CSC credentials/info."""
    cert_block = cert_info.get("cert")
    raw_list: object = (
        cast("dict[str, Any]", cert_block).get("certificates")
        if isinstance(cert_block, dict)
        else cert_info.get("certificates")
    )
    if not isinstance(raw_list, list) or not raw_list:
        raise AssinaturaDigitalInvalidaError(
            f"Cadeia de certificados ausente na resposta do PSC '{provider}'."
        )
    raw_items = cast("list[object]", raw_list)
    parsed = [_decodificar_certificado(item, provider) for item in raw_items]
    store = SimpleCertificateStore()
    for cert in parsed:
        store.register(cert)
    return parsed[0], store


def _decodificar_cms_container(
    cms_b64: str,
    provider: str,
    max_bytes: int,
) -> asn1_cms.ContentInfo:
    """Decode and verify a SignedData CMS container returned by Cloud PSC."""
    try:
        cms_bytes = base64.b64decode(cms_b64.strip(), validate=True)
        content_info = cast(
            "asn1_cms.ContentInfo",
            asn1_cms.ContentInfo.load(cms_bytes),  # pyright: ignore[reportUnknownMemberType]
        )
    except (binascii.Error, ValueError) as err:
        raise AssinaturaDigitalInvalidaError(
            f"Container CMS inválido retornado pelo PSC '{provider}': {err}"
        ) from err

    content_type = str(content_info["content_type"].native)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
    if content_type != "signed_data":
        raise AssinaturaDigitalInvalidaError(
            f"CMS inválido do PSC '{provider}': content_type='{content_type}', "
            "esperado 'signed_data'."
        )
    if len(cms_bytes) > max_bytes:
        raise AssinaturaDigitalInvalidaError(
            f"Container CMS do PSC '{provider}' excede reserva "
            f"({len(cms_bytes)} > {max_bytes})."
        )
    return content_info


class CloudPSCOAuth2Client:
    """HTTP client communicating with Brazilian Cloud PSCs (CSC standard)."""

    def __init__(
        self,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        provider_endpoints: Mapping[str, str] | None = None,
    ) -> None:
        self._timeout = timeout
        self._transport = transport
        source = provider_endpoints or DEFAULT_PSC_ENDPOINTS
        self._provider_endpoints = {
            k.strip().lower(): v.rstrip("/") for k, v in source.items()
        }

    def get_provider_base_url(self, provider: str) -> str:
        """Resolve base URL for target Brazilian Trust Service Provider."""
        prov_clean = provider.strip().lower()
        base_url = self._provider_endpoints.get(prov_clean)
        if base_url:
            return base_url

        raise AssinaturaDigitalInvalidaError(
            f"Provedor PSC não suportado: '{provider}'. "
            "Provedores homologados: 'birdid', 'safeid', 'vidaas', 'fake'."
        )

    async def obter_info_credencial(
        self,
        provider: str,
        token: str,
        credential_id: str | None = None,
    ) -> dict[str, Any]:
        """Query certificate details from Cloud PSC via CSC protocol."""
        base_url = self.get_provider_base_url(provider)
        endpoint = f"{base_url}/csc/v1/credentials/info"
        headers = {
            "Authorization": f"Bearer {token.strip()}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {"certificates": "chain"}
        if credential_id:
            body["credentialID"] = credential_id

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                resp = await client.post(endpoint, json=body, headers=headers)
                if resp.status_code in (401, 403):
                    raise AssinaturaDigitalInvalidaError(
                        "Token de autorização do médico expirado ou não autorizado "
                        f"no provedor PSC '{provider}'."
                    )
                resp.raise_for_status()
                data: object = resp.json()
                if isinstance(data, dict):
                    return cast("dict[str, Any]", data)
                return {}
        except httpx.HTTPError as err:
            raise AssinaturaDigitalInvalidaError(
                f"Falha de comunicação com o provedor PSC '{provider}': {err}"
            ) from err

    @staticmethod
    def _extrair_primeira_assinatura(result: object) -> str | None:
        """Extrai a primeira assinatura da resposta CSC signHash."""
        if not isinstance(result, dict):
            return None
        res_dict = cast("dict[str, Any]", result)
        sigs: object = res_dict.get("signatures")
        if isinstance(sigs, list) and sigs and isinstance(sigs[0], str):
            return sigs[0]
        sig: object = res_dict.get("signature")
        if isinstance(sig, str) and sig.strip():
            return sig.strip()
        return None

    async def assinar_hash(
        self,
        provider: str,
        token: str,
        credential_id: str,
        hash_b64: str,
        sign_algo: str = "1.2.840.113549.1.1.1",
        response_format: str | None = None,
    ) -> str:
        """Request remote digital signature of SHA-256 digest via CSC signHash."""
        base_url = self.get_provider_base_url(provider)
        endpoint = f"{base_url}/csc/v1/signatures/signHash"
        headers = {
            "Authorization": f"Bearer {token.strip()}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "credentialID": credential_id,
            "hashes": [hash_b64],
            "hashAlgorithmOID": "2.16.840.1.101.3.4.2.1",  # SHA-256
            "signAlgo": sign_algo,
        }
        if response_format:
            body["responseFormat"] = response_format

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                resp = await client.post(endpoint, json=body, headers=headers)
                if resp.status_code in (401, 403):
                    raise AssinaturaDigitalInvalidaError(
                        f"Acesso negado pelo PSC '{provider}' ao assinar documento."
                    )
                resp.raise_for_status()
                assinatura = self._extrair_primeira_assinatura(resp.json())
                if assinatura is not None:
                    return assinatura
                raise AssinaturaDigitalInvalidaError(
                    f"Resposta inválida do PSC '{provider}': formato inesperado."
                )
        except httpx.HTTPError as err:
            raise AssinaturaDigitalInvalidaError(
                f"Erro na requisição de assinatura junto ao PSC '{provider}': {err}"
            ) from err


class FakeICPBrasilSigner(ICPBrasilSignerPort):
    """In-memory cryptographic signer generating genuine PAdES PDF structures."""

    def __init__(self) -> None:
        self._key: rsa.RSAPrivateKey | None = None
        self._cert_pem: bytes | None = None
        self._key_pem: bytes | None = None
        self.last_credentials: DoctorCertificateCredentials | None = None
        self.last_metadata: SignatureMetadataDTO | None = None
        self.last_signed_bytes: bytes | None = None

    def _ensure_crypto_material(self) -> None:
        """Lazily initialize RSA key and ICP-Brasil test X.509 certificate."""
        if self._key is not None and self._cert_pem and self._key_pem:
            return

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "DF"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ICP-Brasil Test"),
                x509.NameAttribute(NameOID.COMMON_NAME, "DR. MEDICO TESTE:00000000000"),
            ]
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(days=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=365))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .sign(key, hashes.SHA256())
        )

        self._key = key
        self._cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        self._key_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

    async def assinar_pdf(
        self,
        pdf_bytes: bytes,
        credenciais: DoctorCertificateCredentials,
        metadata: SignatureMetadataDTO | None = None,
    ) -> bytes:
        """Apply genuine PAdES signature using the test certificate."""
        if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
            raise AssinaturaDigitalInvalidaError(
                "Conteúdo fornecido não é um arquivo PDF válido."
            )

        if not credenciais.token or not credenciais.token.strip():
            raise AssinaturaDigitalInvalidaError(
                "Token de autorização do médico não pode ser vazio."
            )

        self._ensure_crypto_material()
        if self._cert_pem is None or self._key_pem is None:
            raise AssinaturaDigitalInvalidaError(
                "Falha ao carregar material criptográfico de teste."
            )

        meta_dto = metadata or SignatureMetadataDTO()
        self.last_credentials = credenciais
        self.last_metadata = meta_dto

        signing_cert = cast(
            "asn1_x509.Certificate",
            next(iter(load_certs_from_pemder_data(self._cert_pem))),  # pyright: ignore[reportUnknownArgumentType]
        )
        signing_key = load_private_key_from_pemder_data(self._key_pem, passphrase=None)

        cert_store = SimpleCertificateStore()
        cert_store.register(signing_cert)

        simple_signer = signers.SimpleSigner(
            signing_cert=signing_cert,
            signing_key=signing_key,
            cert_registry=cert_store,
        )

        in_stream = io.BytesIO(pdf_bytes)
        writer = IncrementalPdfFileWriter(in_stream)
        out_stream = io.BytesIO()

        field_name = f"{meta_dto.field_name}_{uuid4().hex[:8]}"

        pdf_meta = signers.PdfSignatureMetadata(
            field_name=field_name,
            reason=meta_dto.reason,
            location=meta_dto.location,
        )

        pdf_signer = signers.PdfSigner(
            signature_meta=pdf_meta,
            signer=simple_signer,
        )

        await pdf_signer.async_sign_pdf(  # pyright: ignore[reportUnknownMemberType]
            writer, output=out_stream
        )
        signed_bytes = out_stream.getvalue()
        self.last_signed_bytes = signed_bytes
        return signed_bytes


class PyHankoSigner(ICPBrasilSignerPort):
    """PAdES digital signer supporting Cloud PSCs and local test execution."""

    def __init__(
        self,
        psc_client: CloudPSCOAuth2Client | None = None,
        fake_signer: FakeICPBrasilSigner | None = None,
        allow_fake: bool = True,
    ) -> None:
        self._psc_client = psc_client or CloudPSCOAuth2Client()
        self._fake_signer = fake_signer or FakeICPBrasilSigner()
        self._allow_fake = allow_fake

    async def assinar_pdf(
        self,
        pdf_bytes: bytes,
        credenciais: DoctorCertificateCredentials,
        metadata: SignatureMetadataDTO | None = None,
    ) -> bytes:
        """Apply PAdES signature via PyHanko ExternalSigner or Fake test signer."""
        _validar_entrada_assinatura(pdf_bytes, credenciais)
        prov = credenciais.provider.strip().lower()

        if prov in ("fake", "mock", "local"):
            if not self._allow_fake:
                raise AssinaturaDigitalInvalidaError(
                    f"Provedor simulado '{prov}' desabilitado neste ambiente."
                )
            return await self._fake_signer.assinar_pdf(pdf_bytes, credenciais, metadata)

        meta_dto = metadata or SignatureMetadataDTO()
        alias = credenciais.certificate_alias or "default-credential"
        return await self._assinar_via_cloud_psc(
            pdf_bytes=pdf_bytes,
            provider=prov,
            token=credenciais.token,
            credential_id=alias,
            meta_dto=meta_dto,
        )

    async def _assinar_via_cloud_psc(
        self,
        *,
        pdf_bytes: bytes,
        provider: str,
        token: str,
        credential_id: str,
        meta_dto: SignatureMetadataDTO,
    ) -> bytes:
        """Prepare TBS ByteRange digest via ExternalSigner and embed PSC CMS."""
        try:
            cert_info = await self._psc_client.obter_info_credencial(
                provider=provider,
                token=token,
                credential_id=credential_id,
            )
            signing_cert, cert_store = _carregar_certificados_psc(cert_info, provider)

            ext_signer = signers.ExternalSigner(
                signing_cert=signing_cert,
                cert_registry=cert_store,
                signature_value=256,
            )
            pdf_meta = signers.PdfSignatureMetadata(
                field_name=f"{meta_dto.field_name}_{uuid4().hex[:8]}",
                reason=meta_dto.reason,
                location=meta_dto.location,
            )
            pdf_signer = signers.PdfSigner(signature_meta=pdf_meta, signer=ext_signer)
            writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
            signing_session = pdf_signer.init_signing_session(writer)
            validation_info = await signing_session.perform_presign_validation(writer)
            estimated = await signing_session.estimate_signature_container_size(  # pyright: ignore[reportUnknownMemberType]
                validation_info
            )
            bytes_reserved = max(int(estimated), _CLOUD_CMS_RESERVED_BYTES)
            tbs_doc: Any = signing_session.prepare_tbs_document(  # pyright: ignore[reportUnknownMemberType]
                validation_info=validation_info,
                bytes_reserved=bytes_reserved,
            )
            prepared_pair: tuple[Any, io.BytesIO] = tbs_doc.digest_tbs_document()
            prepared_digest, res_output = prepared_pair

            hash_b64 = base64.b64encode(prepared_digest.document_digest).decode("ascii")
            cms_b64 = await self._psc_client.assinar_hash(
                provider=provider,
                token=token,
                credential_id=credential_id,
                hash_b64=hash_b64,
                response_format="cms",
            )
            cms_obj = _decodificar_cms_container(cms_b64, provider, bytes_reserved)
            await PdfTBSDocument.async_finish_signing(  # pyright: ignore[reportUnknownMemberType]
                res_output, prepared_digest, cms_obj
            )
            return res_output.getvalue()
        except AssinaturaDigitalInvalidaError:
            raise
        except Exception as err:
            raise AssinaturaDigitalInvalidaError(
                f"Erro inesperado ao assinar via provedor PSC '{provider}': {err}"
            ) from err
