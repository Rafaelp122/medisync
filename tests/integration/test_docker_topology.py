"""Integration test suite validating local Docker container topology."""

import socket
import subprocess
import urllib.request

import pytest


def _is_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is open and accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def check_docker_services_running() -> None:
    """Fixture ensuring Docker containers are running before test execution."""
    if not _is_port_open("localhost", 5432):
        pytest.skip("PostgreSQL (port 5432) is not reachable. Run 'just up' first.")


def test_tcp_ports_available(check_docker_services_running: None) -> None:
    """Validate that all 4 required service ports are open and listening."""
    services: dict[str, int] = {
        "postgres": 5432,
        "valkey": 6379,
        "livekit": 7880,
        "minio_s3": 9000,
        "minio_console": 9001,
    }
    for service_name, port in services.items():
        assert _is_port_open("localhost", port), (
            f"Service {service_name} is not responding on port {port}"
        )


def test_postgres_extensions(check_docker_services_running: None) -> None:
    """Verify that PostgreSQL 17 has uuid-ossp and pgcrypto extensions installed."""
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "medisync",
            "-d",
            "medisync",
            "-tAc",
            "SELECT extname FROM pg_extension;",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    extensions = [
        line.strip() for line in result.stdout.strip().splitlines() if line.strip()
    ]
    assert "uuid-ossp" in extensions, f"uuid-ossp not found in {extensions}"
    assert "pgcrypto" in extensions, f"pgcrypto not found in {extensions}"


def test_valkey_ping(check_docker_services_running: None) -> None:
    """Verify that Valkey 8.0 responds to PING command with PONG."""
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "valkey", "valkey-cli", "ping"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "PONG"


def test_livekit_http_endpoint(check_docker_services_running: None) -> None:
    """Verify that LiveKit SFU server responds on port 7880."""
    req = urllib.request.Request("http://localhost:7880")
    with urllib.request.urlopen(req, timeout=5.0) as response:
        assert response.status == 200
        content = response.read().decode("utf-8").strip()
        assert content == "OK"


def test_minio_s3_and_console(check_docker_services_running: None) -> None:
    """Verify that MinIO S3 API and Console endpoints are reachable."""
    with urllib.request.urlopen(
        "http://localhost:9000/minio/health/live", timeout=5.0
    ) as response:
        assert response.status == 200

    with urllib.request.urlopen("http://localhost:9001/", timeout=5.0) as response:
        assert response.status == 200


def test_minio_default_bucket(check_docker_services_running: None) -> None:
    """Verify that MinIO default bucket 'medisync-docs' is provisioned."""
    subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "minio",
            "mc",
            "alias",
            "set",
            "testalias",
            "http://localhost:9000",
            "medisync",
            "medisync123",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "minio", "mc", "ls", "testalias/"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "medisync-docs/" in result.stdout
