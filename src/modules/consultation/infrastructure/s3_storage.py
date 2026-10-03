"""Object Storage (S3 / MinIO) adapters for clinical documents."""

from typing import Any, cast

import aioboto3
from botocore.exceptions import ClientError

from src.core.config import get_settings
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.domain.exceptions import (
    DocumentoNaoEncontradoNoStorageError,
)


class S3StorageAdapter(StoragePort):
    """Asynchronous Object Storage adapter backed by AWS S3 or MinIO via aioboto3."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        bucket_name: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self._endpoint_url = endpoint_url or settings.S3_ENDPOINT_URL
        self._bucket_name = bucket_name or settings.S3_BUCKET_NAME
        self._access_key = access_key or settings.S3_ACCESS_KEY_ID
        self._secret_key = secret_key or settings.S3_SECRET_ACCESS_KEY
        self._region_name = region_name or settings.S3_REGION_NAME
        self._session = aioboto3.Session()

    def _client(self) -> Any:
        return cast(
            "Any",
            self._session.client(  # pyright: ignore[reportUnknownMemberType]
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region_name,
            ),
        )

    async def salvar_documento(
        self,
        chave: str,
        conteudo: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        """Persist binary document to S3/MinIO bucket."""
        async with self._client() as s3:
            await s3.put_object(  # pyright: ignore[reportUnknownMemberType]
                Bucket=self._bucket_name,
                Key=chave,
                Body=conteudo,
                ContentType=content_type,
            )
        return chave

    async def obter_documento(self, chave: str) -> bytes:
        """Retrieve binary document bytes by object key from S3/MinIO."""
        try:
            async with self._client() as s3:
                resp: dict[str, Any] = await s3.get_object(  # pyright: ignore[reportUnknownMemberType]
                    Bucket=self._bucket_name, Key=chave
                )
                body: Any = resp["Body"]
                raw_bytes: Any = await body.read()  # pyright: ignore[reportUnknownMemberType]
                return bytes(raw_bytes)
        except ClientError as err:
            code = ""
            resp_obj: object = getattr(err, "response", None)
            if isinstance(resp_obj, dict):
                resp_dict = cast("dict[str, object]", resp_obj)
                err_obj = resp_dict.get("Error")
                if isinstance(err_obj, dict):
                    err_dict = cast("dict[str, object]", err_obj)
                    code_val = err_dict.get("Code")
                    if isinstance(code_val, str):
                        code = code_val
            if code in ("NoSuchKey", "404", "NotFound"):
                raise DocumentoNaoEncontradoNoStorageError(
                    f"Documento com chave '{chave}' não encontrado no storage."
                ) from err
            raise

    async def gerar_url_pre_assinada(
        self,
        chave: str,
        expiracao_segundos: int = 300,
    ) -> str:
        """Generate time-limited presigned URL for secure download."""
        async with self._client() as s3:
            url: Any = await s3.generate_presigned_url(  # pyright: ignore[reportUnknownMemberType]
                ClientMethod="get_object",
                Params={"Bucket": self._bucket_name, "Key": chave},
                ExpiresIn=expiracao_segundos,
            )
            return str(url)


class FakeStorageAdapter(StoragePort):
    """In-memory storage adapter for automated test suites and local validation."""

    def __init__(
        self,
        bucket_name: str = "medisync-docs",
        base_presigned_url: str = "https://storage.medisync.local",
    ) -> None:
        self._bucket_name = bucket_name
        self._base_presigned_url = base_presigned_url.rstrip("/")
        self._storage: dict[str, bytes] = {}

    async def salvar_documento(
        self,
        chave: str,
        conteudo: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        """Store bytes in memory mapping."""
        self._storage[chave] = conteudo
        return chave

    async def obter_documento(self, chave: str) -> bytes:
        """Retrieve bytes from memory mapping or raise 404."""
        if chave not in self._storage:
            raise DocumentoNaoEncontradoNoStorageError(
                f"Documento com chave '{chave}' não encontrado no storage."
            )
        return self._storage[chave]

    async def gerar_url_pre_assinada(
        self,
        chave: str,
        expiracao_segundos: int = 300,
    ) -> str:
        """Return deterministic mock presigned URL."""
        if chave not in self._storage:
            raise DocumentoNaoEncontradoNoStorageError(
                f"Documento com chave '{chave}' não encontrado no storage."
            )
        return (
            f"{self._base_presigned_url}/{self._bucket_name}/{chave}"
            f"?expires_in={expiracao_segundos}&token=mock-presigned-token"
        )

    def contains(self, chave: str) -> bool:
        """Check if an object key exists in memory."""
        return chave in self._storage

    def clear(self) -> None:
        """Clear all stored objects."""
        self._storage.clear()
