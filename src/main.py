"""MediSync Express — FastAPI Application Entrypoint."""

from fastapi import FastAPI
from pydantic import BaseModel

from src.core.config import get_settings
from src.core.context import get_current_request_id, get_current_tenant_id
from src.core.errors import register_exception_handlers
from src.core.logging import setup_logging
from src.core.middleware import setup_middlewares


class HealthCheckResponse(BaseModel):
    status: str
    version: str
    tenant_id: int | None
    request_id: str | None


def create_app() -> FastAPI:
    """Application factory for MediSync Express API."""
    settings = get_settings()
    setup_logging(level="DEBUG" if settings.DEBUG else "INFO")

    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 1. Register RFC 7807 exception handlers
    register_exception_handlers(app)

    # 2. Setup HTTP middlewares pipeline
    setup_middlewares(app)

    # 3. System health route
    @app.get("/healthz", response_model=HealthCheckResponse)
    async def healthcheck() -> HealthCheckResponse:
        return HealthCheckResponse(
            status="ok",
            version="0.1.0",
            tenant_id=get_current_tenant_id(),
            request_id=get_current_request_id(),
        )

    return app


app = create_app()
