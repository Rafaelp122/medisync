"""Unit tests for S3/MinIO Object Storage adapters and LGPD masking."""

from typing import Any

import pytest
from botocore.exceptions import ClientError
from src.core.privacy import mascarar_cpf, mascarar_nome
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.domain.exceptions import (
    DocumentoNaoEncontradoNoStorageError,
)
from src.modules.consultation.infrastructure.s3_storage import (
    FakeStorageAdapter,
    S3StorageAdapter,
)

from tests.doubles import FakeS3Session


def test_storage_port_conformance() -> None:
    """Validate that FakeStorageAdapter and S3StorageAdapter satisfy StoragePort."""
    fake = FakeStorageAdapter()
    assert isinstance(fake, StoragePort)

    s3_adapter = S3StorageAdapter()
    assert isinstance(s3_adapter, StoragePort)


@pytest.mark.asyncio
async def test_fake_storage_adapter_save_and_retrieve() -> None:
    """Validate in-memory persistence and retrieval of document bytes."""
    storage = FakeStorageAdapter(bucket_name="test-bucket")
    test_key = "consultations/123/documents/abc.pdf"
    content = b"%PDF-1.4 Mock Binary Document Content"

    returned_key = await storage.salvar_documento(test_key, content)
    assert returned_key == test_key
    assert storage.contains(test_key)

    retrieved = await storage.obter_documento(test_key)
    assert retrieved == content

    url = await storage.gerar_url_pre_assinada(test_key, expiracao_segundos=600)
    assert "test-bucket" in url
    assert test_key in url
    assert "expires_in=600" in url

    storage.clear()
    assert not storage.contains(test_key)


@pytest.mark.asyncio
async def test_fake_storage_adapter_key_not_found() -> None:
    """Ensure absent keys in FakeStorageAdapter raise storage not found error."""
    storage = FakeStorageAdapter()

    with pytest.raises(DocumentoNaoEncontradoNoStorageError):
        await storage.obter_documento("non-existent.pdf")

    with pytest.raises(DocumentoNaoEncontradoNoStorageError):
        await storage.gerar_url_pre_assinada("non-existent.pdf")


@pytest.mark.asyncio
async def test_s3_storage_adapter_salvar_documento() -> None:
    """Validate S3StorageAdapter puts object to S3 via injected session."""
    fake_session = FakeS3Session()
    adapter = S3StorageAdapter(
        endpoint_url="http://mock-minio:9000",
        bucket_name="my-bucket",
        access_key="key",
        secret_key="secret",
        region_name="us-east-1",
        session=fake_session,
    )

    key = "documents/test.pdf"
    data = b"raw pdf data"
    saved = await adapter.salvar_documento(key, data, content_type="application/pdf")

    assert saved == key
    assert fake_session.put_calls == [
        {
            "Bucket": "my-bucket",
            "Key": key,
            "Body": data,
            "ContentType": "application/pdf",
        }
    ]
    assert fake_session.objects[("my-bucket", key)] == data


@pytest.mark.asyncio
async def test_s3_storage_adapter_obter_documento_success() -> None:
    """Validate S3StorageAdapter retrieves object body bytes."""
    fake_session = FakeS3Session(
        objects={("my-bucket", "documents/doc.pdf"): b"retrieved file content"}
    )
    adapter = S3StorageAdapter(bucket_name="my-bucket", session=fake_session)

    content = await adapter.obter_documento("documents/doc.pdf")
    assert content == b"retrieved file content"
    assert fake_session.get_calls == [
        {"Bucket": "my-bucket", "Key": "documents/doc.pdf"}
    ]


@pytest.mark.asyncio
async def test_s3_storage_adapter_obter_documento_not_found() -> None:
    """Validate S3StorageAdapter translates NoSuchKey into 404 domain error."""
    error_response: dict[str, Any] = {
        "Error": {"Code": "NoSuchKey", "Message": "Key not found"}
    }
    fake_session = FakeS3Session(get_error=ClientError(error_response, "GetObject"))
    adapter = S3StorageAdapter(bucket_name="my-bucket", session=fake_session)

    with pytest.raises(DocumentoNaoEncontradoNoStorageError):
        await adapter.obter_documento("documents/missing.pdf")


@pytest.mark.asyncio
async def test_s3_storage_adapter_obter_documento_other_error() -> None:
    """Validate S3StorageAdapter bubbles up non-404 ClientErrors."""
    error_response: dict[str, Any] = {
        "Error": {"Code": "AccessDenied", "Message": "Forbidden"}
    }
    fake_session = FakeS3Session(get_error=ClientError(error_response, "GetObject"))
    adapter = S3StorageAdapter(bucket_name="my-bucket", session=fake_session)

    with pytest.raises(ClientError):
        await adapter.obter_documento("documents/secret.pdf")


@pytest.mark.asyncio
async def test_s3_storage_adapter_gerar_url_pre_assinada() -> None:
    """Validate S3StorageAdapter calls generate_presigned_url."""
    expected_url = "https://s3.amazonaws.com/my-bucket/key.pdf?signature=valid"
    fake_session = FakeS3Session(presigned_url=expected_url)
    adapter = S3StorageAdapter(bucket_name="my-bucket", session=fake_session)

    url = await adapter.gerar_url_pre_assinada("key.pdf", expiracao_segundos=180)
    assert url == expected_url
    assert fake_session.presign_calls == [
        {
            "ClientMethod": "get_object",
            "Params": {"Bucket": "my-bucket", "Key": "key.pdf"},
            "ExpiresIn": 180,
        }
    ]


def test_lgpd_cpf_masking() -> None:
    """Validate that patient CPF is masked to protect sensitive personal data."""
    assert mascarar_cpf("111.222.333-44") == "111.***.***-44"
    assert mascarar_cpf("12345678901") == "123.***.***-01"
    assert mascarar_cpf("invalid") == "***.***.***-**"
    assert mascarar_cpf("") == "***.***.***-**"


def test_lgpd_name_masking() -> None:
    """Validate that patient name has subsequent letters masked per word."""
    assert mascarar_nome("Maria Joana dos Santos") == "M**** J**** dos S*****"
    assert mascarar_nome("Ana de Souza") == "A** de S****"
    assert mascarar_nome("") == "***"
    assert mascarar_nome("   ") == "***"
