"""Port specification for Object Storage (S3 / MinIO) for clinical documents."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class StoragePort(Protocol):
    """Port interface for storing and retrieving documents in Object Storage."""

    async def salvar_documento(
        self,
        chave: str,
        conteudo: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        """Persist binary document to Object Storage.

        Args:
            chave: Structured path / object key in bucket.
            conteudo: Raw file bytes to persist.
            content_type: MIME type of the document.

        Returns:
            The stored object key.
        """
        ...

    async def obter_documento(self, chave: str) -> bytes:
        """Retrieve binary document bytes by object key.

        Args:
            chave: Stored object key in bucket.

        Returns:
            Raw file bytes.
        """
        ...

    async def gerar_url_pre_assinada(
        self,
        chave: str,
        expiracao_segundos: int = 300,
    ) -> str:
        """Generate short-lived presigned URL for secure temporary download.

        Args:
            chave: Stored object key in bucket.
            expiracao_segundos: Time-to-live for the presigned URL (default 300s).

        Returns:
            Complete presigned HTTPS/HTTP download URL.
        """
        ...
