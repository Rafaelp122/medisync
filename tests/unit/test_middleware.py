from uuid import uuid4

from src.core.authz.roles import Role
from src.core.config import get_settings
from src.core.middleware import (
    extract_tenant_from_auth_header,
    extract_tenant_from_header,
    extract_tenant_from_host,
)

from tests.unit.test_authz_rbac import create_test_token


def test_extract_tenant_from_header():
    assert extract_tenant_from_header("101") == 101
    assert extract_tenant_from_header("   42   ") == 42
    assert extract_tenant_from_header(None) is None
    assert extract_tenant_from_header("invalid") is None
    assert extract_tenant_from_header("-5") is None
    assert extract_tenant_from_header("0") is None


def test_extract_tenant_from_host():
    assert extract_tenant_from_host("101.medisync.local") == 101
    assert extract_tenant_from_host("tenant-42.medisync.local") == 42
    assert extract_tenant_from_host("101.medisync.local:8000") == 101
    assert extract_tenant_from_host("tenant-42.medisync.local:443") == 42
    assert extract_tenant_from_host("medisync.com.br") is None
    assert extract_tenant_from_host("localhost:8000") is None
    assert extract_tenant_from_host("127.0.0.1:8000") is None
    assert extract_tenant_from_host("192.168.1.100") is None
    assert extract_tenant_from_host("api.medisync.com.br") is None
    assert extract_tenant_from_host(None) is None


def test_extract_tenant_from_auth_header():
    settings = get_settings()
    valid_token = create_test_token(
        usuario_id=uuid4(),
        organizacao_id=77,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
    )

    # Valid Bearer token
    assert extract_tenant_from_auth_header(f"Bearer {valid_token}") == 77
    assert extract_tenant_from_auth_header(f"bearer   {valid_token}  ") == 77

    # Missing / None
    assert extract_tenant_from_auth_header(None) is None
    assert extract_tenant_from_auth_header("") is None

    # Invalid schemes
    assert extract_tenant_from_auth_header(f"Basic {valid_token}") is None
    assert extract_tenant_from_auth_header("InvalidFormat") is None

    # Tampered / invalid token
    assert extract_tenant_from_auth_header("Bearer invalid.token.payload") is None
    bad_secret_token = create_test_token(
        usuario_id=uuid4(),
        organizacao_id=77,
        papel=Role.MEDICO,
        secret_key="wrong_secret_key_1234567890123456",
    )
    assert extract_tenant_from_auth_header(f"Bearer {bad_secret_token}") is None
