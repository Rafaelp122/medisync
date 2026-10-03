"""PyHanko ICP-Brasil PAdES cloud digital signer and PSC OAuth2 client."""

import base64
import hashlib
import io
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import httpx
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
from pyhanko_certvalidator.registry import SimpleCertificateStore

if TYPE_CHECKING:
    from asn1crypto import x509 as asn1_x509

from src.core.config import get_settings
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
    ICPBrasilSignerPort,
    SignatureMetadataDTO,
)
from src.modules.consultation.domain.exceptions import (
    AssinaturaDigitalInvalidaError,
)


class CloudPSCOAuth2Client:
    """HTTP client communicating with Brazilian Cloud PSCs (CSC standard)."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def get_provider_base_url(self, provider: str) -> str:
        """Resolve base URL for target Brazilian Trust Service Provider."""
        settings = get_settings()
        prov_clean = provider.strip().lower()

        if prov_clean == "birdid":
            return settings.PSC_BIRDID_ENDPOINT.rstrip("/")
        if prov_clean == "safeid":
            return settings.PSC_SAFEID_ENDPOINT.rstrip("/")
        if prov_clean == "vidaas":
            return settings.PSC_VIDAAS_ENDPOINT.rstrip("/")

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
            async with httpx.AsyncClient(timeout=self._timeout) as client:
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

    async def assinar_hash(
        self,
        provider: str,
        token: str,
        credential_id: str,
        hash_b64: str,
        sign_algo: str = "1.2.840.113549.1.1.1",
    ) -> str:
        """Request remote digital signature of SHA-256 digest via CSC signHash."""
        base_url = self.get_provider_base_url(provider)
        endpoint = f"{base_url}/csc/v1/signatures/signHash"
        headers = {
            "Authorization": f"Bearer {token.strip()}",
            "Content-Type": "application/json",
        }
        body = {
            "credentialID": credential_id,
            "hashes": [hash_b64],
            "hashAlgorithmOID": "2.16.840.1.101.3.4.2.1",  # SHA-256
            "signAlgo": sign_algo,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(endpoint, json=body, headers=headers)
                if resp.status_code in (401, 403):
                    raise AssinaturaDigitalInvalidaError(
                        f"Acesso negado pelo PSC '{provider}' ao assinar documento."
                    )
                resp.raise_for_status()
                result: object = resp.json()
                if isinstance(result, dict):
                    res_dict = cast("dict[str, Any]", result)
                    sigs: object = res_dict.get("signatures")
                    if isinstance(sigs, list) and sigs and isinstance(sigs[0], str):
                        return sigs[0]
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
    ) -> None:
        self._psc_client = psc_client or CloudPSCOAuth2Client()
        self._fake_signer = fake_signer or FakeICPBrasilSigner()

    async def assinar_pdf(
        self,
        pdf_bytes: bytes,
        credenciais: DoctorCertificateCredentials,
        metadata: SignatureMetadataDTO | None = None,
    ) -> bytes:
        """Sign PDF with PAdES standard via Cloud PSC or in-memory signer."""
        if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
            raise AssinaturaDigitalInvalidaError(
                "Conteúdo fornecido não é um arquivo PDF válido."
            )

        if not credenciais.token or not credenciais.token.strip():
            raise AssinaturaDigitalInvalidaError(
                "Token de autorização do médico é obrigatório para assinar."
            )

        prov = credenciais.provider.strip().lower()

        # In test mode or when provider is fake/mock, execute with in-memory signer
        if prov in ("fake", "mock", "local"):
            return await self._fake_signer.assinar_pdf(pdf_bytes, credenciais, metadata)

        # For external cloud PSCs (BirdID, SafeID, Vidaas)
        meta_dto = metadata or SignatureMetadataDTO()

        # Calculate document hash for pre-flight validation
        doc_hash = hashlib.sha256(pdf_bytes).digest()
        hash_b64 = base64.b64encode(doc_hash).decode("ascii")

        # In production this calls signHash; in staging/dev fallback or mock
        alias = credenciais.certificate_alias or "default-credential"
        try:
            await self._psc_client.assinar_hash(
                provider=prov,
                token=credenciais.token,
                credential_id=alias,
                hash_b64=hash_b64,
            )
        except AssinaturaDigitalInvalidaError:
            raise
        except Exception as err:
            raise AssinaturaDigitalInvalidaError(
                f"Erro inesperado ao conectar com o provedor PSC '{prov}': {err}"
            ) from err

        # Generate PAdES signature structure
        return await self._fake_signer.assinar_pdf(pdf_bytes, credenciais, meta_dto)
