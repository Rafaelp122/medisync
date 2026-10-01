from src.core.middleware import extract_tenant_from_header, extract_tenant_from_host


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
