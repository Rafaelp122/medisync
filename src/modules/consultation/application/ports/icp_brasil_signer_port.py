"""Port and DTO specifications for ICP-Brasil PAdES cloud digital signing."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class DoctorCertificateCredentials:
    """Credentials and OAuth2 token to authorize remote cloud signature with PSC."""

    token: str
    provider: str = "birdid"
    certificate_alias: str | None = None


@dataclass(frozen=True)
class SignatureMetadataDTO:
    """Metadata embedded into the PAdES cryptographic dictionary."""

    reason: str = "Documento emitido nos termos da Resolução CFM nº 2.314/2022"
    location: str = "Brasil"
    contact_info: str | None = None
    field_name: str = "Assinatura_ICP_Brasil"


@runtime_checkable
class ICPBrasilSignerPort(Protocol):
    """Port interface for signing PDF/A documents with ICP-Brasil standard."""

    async def assinar_pdf(
        self,
        pdf_bytes: bytes,
        credenciais: DoctorCertificateCredentials,
        metadata: SignatureMetadataDTO | None = None,
    ) -> bytes:
        """Apply PAdES digital signature on raw PDF bytes.

        Args:
            pdf_bytes: Archivable PDF/A bytes to be signed.
            credenciais: Physician cloud PSC OAuth2 token and provider identifier.
            metadata: Optional reason, location, and field metadata for the signature.

        Returns:
            Cryptographically signed PDF binary matching PAdES specification.
        """
        ...
