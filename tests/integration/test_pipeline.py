import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field
from src.core.context import get_current_tenant_id
from src.core.errors import ConflictError, NotFoundError
from src.core.uuid7 import is_valid_uuid, uuid7_str
from src.main import create_app


class SamplePayload(BaseModel):
    name: str = Field(min_length=3)
    age: int = Field(ge=0)


@pytest.fixture
def app_with_routes() -> FastAPI:
    test_app = create_app()

    @test_app.get("/test/domain-error")
    async def route_domain_error() -> None:
        raise NotFoundError("Patient not found with specified ID")

    @test_app.get("/test/conflict-error")
    async def route_conflict_error() -> None:
        raise ConflictError("Patient already queued")

    @test_app.post("/test/validation-error")
    async def route_validation_error(
        payload: SamplePayload,
    ) -> dict[str, str]:
        return {"received": payload.name}

    @test_app.get("/test/unhandled-error")
    async def route_unhandled_error() -> None:
        raise RuntimeError("Secret database password / catastrophic crash")

    @test_app.get("/test/tenant-check")
    async def route_tenant_check() -> dict[str, int | None]:
        return {"tenant_id": get_current_tenant_id()}

    return test_app


@pytest.mark.asyncio
async def test_healthcheck_returns_request_id(
    app_with_routes: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_routes), base_url="http://test"
    ) as client:
        res = await client.get("/healthz")
        assert res.status_code == 200
        assert "x-request-id" in res.headers
        req_id = res.headers["x-request-id"]
        assert is_valid_uuid(req_id)
        data = res.json()
        assert data["status"] == "ok"
        assert data["request_id"] == req_id


@pytest.mark.asyncio
async def test_propagates_incoming_request_id(
    app_with_routes: FastAPI,
) -> None:
    custom_id = uuid7_str()
    async with AsyncClient(
        transport=ASGITransport(app=app_with_routes), base_url="http://test"
    ) as client:
        res = await client.get("/healthz", headers={"X-Request-ID": custom_id})
        assert res.status_code == 200
        assert res.headers["x-request-id"] == custom_id
        assert res.json()["request_id"] == custom_id


@pytest.mark.asyncio
async def test_replaces_invalid_incoming_request_id(
    app_with_routes: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_routes), base_url="http://test"
    ) as client:
        res = await client.get("/healthz", headers={"X-Request-ID": "invalid-non-uuid"})
        assert res.status_code == 200
        req_id = res.headers["x-request-id"]
        assert req_id != "invalid-non-uuid"
        assert is_valid_uuid(req_id)


@pytest.mark.asyncio
async def test_tenant_resolution_via_header(
    app_with_routes: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_routes), base_url="http://test"
    ) as client:
        res = await client.get("/test/tenant-check", headers={"X-Tenant-ID": "505"})
        assert res.status_code == 200
        assert res.json()["tenant_id"] == 505


@pytest.mark.asyncio
async def test_tenant_resolution_via_subdomain(
    app_with_routes: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_routes), base_url="http://test"
    ) as client:
        res = await client.get(
            "/test/tenant-check", headers={"Host": "tenant-88.medisync.local"}
        )
        assert res.status_code == 200
        assert res.json()["tenant_id"] == 88


@pytest.mark.asyncio
async def test_domain_error_returns_rfc7807(
    app_with_routes: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_routes), base_url="http://test"
    ) as client:
        res = await client.get("/test/domain-error")
        assert res.status_code == 404
        assert res.headers["content-type"].startswith("application/problem+json")
        assert "x-request-id" in res.headers

        body = res.json()
        assert body["status"] == 404
        assert body["title"] == "Not Found"
        assert body["detail"] == "Patient not found with specified ID"
        assert body["code"] == "NOT_FOUND"
        assert body["request_id"] == res.headers["x-request-id"]


@pytest.mark.asyncio
async def test_conflict_error_returns_rfc7807(
    app_with_routes: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_routes), base_url="http://test"
    ) as client:
        res = await client.get("/test/conflict-error")
        assert res.status_code == 409
        assert res.headers["content-type"].startswith("application/problem+json")
        assert "x-request-id" in res.headers

        body = res.json()
        assert body["status"] == 409
        assert body["title"] == "Conflict"
        assert body["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_validation_error_returns_rfc7807(
    app_with_routes: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_routes), base_url="http://test"
    ) as client:
        res = await client.post("/test/validation-error", json={"name": "a", "age": -5})
        assert res.status_code == 422
        assert res.headers["content-type"].startswith("application/problem+json")
        assert "x-request-id" in res.headers

        body = res.json()
        assert body["status"] == 422
        assert body["title"] == "Unprocessable Entity"
        assert "invalid_params" in body
        assert len(body["invalid_params"]) >= 2


@pytest.mark.asyncio
async def test_http_404_returns_rfc7807(app_with_routes: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_routes), base_url="http://test"
    ) as client:
        res = await client.get("/non-existent-route")
        assert res.status_code == 404
        assert res.headers["content-type"].startswith("application/problem+json")
        assert "x-request-id" in res.headers
        body = res.json()
        assert body["status"] == 404
        assert body["title"] == "HTTP Error"


@pytest.mark.asyncio
async def test_unhandled_500_does_not_leak_secrets(
    app_with_routes: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_routes), base_url="http://test"
    ) as client:
        res = await client.get("/test/unhandled-error")
        assert res.status_code == 500
        assert res.headers["content-type"].startswith("application/problem+json")
        assert "x-request-id" in res.headers

        body = res.json()
        assert body["status"] == 500
        assert body["title"] == "Internal Server Error"
        # Must NOT leak secret database message
        assert "catastrophic" not in body["detail"]
        assert "password" not in body["detail"]
        assert body["request_id"] == res.headers["x-request-id"]
