"""MediSync Express — FastAPI Application Entrypoint."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.database import engine
from src.core.errors import register_exception_handlers
from src.core.health_router import health_router
from src.core.logging import setup_logging
from src.core.middleware import setup_middlewares
from src.core.telemetry import setup_telemetry
from src.core.valkey import (
    close_arq_pool,
    close_valkey_pool,
    get_valkey_pool,
)
from src.modules.queue.composition import on_startup as queue_on_startup


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Lifespan context managing application startup and graceful shutdown."""
    logger = logging.getLogger("medisync.lifespan")

    # 1. Preload Lua scripts into Valkey on startup
    try:
        pool = get_valkey_pool()
        await queue_on_startup(pool)
    except Exception as exc:
        logger.warning("Valkey Lua script preloading failed or skipped: %s", exc)

    yield

    # 2. Gracefully teardown connection pools on shutdown
    await engine.dispose()
    logger.info("Database engine connection pool disposed successfully.")
    await close_valkey_pool()
    await close_arq_pool()
    logger.info("Valkey and ARQ connection pools closed successfully.")


def create_app() -> FastAPI:
    """Application factory for MediSync Express API."""
    settings = get_settings()
    setup_logging(level="DEBUG" if settings.DEBUG else "INFO")
    tracer_provider = setup_telemetry()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
        telemetry={
            "tracing": True,
            "metrics": True,
            "logs": True,
            "operation_spans": True,
            "tracer_provider": tracer_provider,
            "exclude": lambda scope: (
                scope.get("path") in {"/healthz", "/docs", "/redoc", "/openapi.json"}
            ),
        },
    )

    # 1. Register RFC 7807 exception handlers
    register_exception_handlers(app)

    # 2. Setup HTTP middlewares pipeline
    setup_middlewares(app)

    # 3. Configure CORSMiddleware
    cors_origins = ["*"] if settings.DEBUG else settings.CORS_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 4. System health route with Valkey telemetry
    app.include_router(health_router)

    from src.modules.auth.presentation.routers import http_router as auth_router
    from src.modules.consultation.presentation.routers import (
        http_router as consultation_router,
    )
    from src.modules.consultation.presentation.routers import (
        ws_router as consultation_ws_router,
    )
    from src.modules.identity.presentation.routers import (
        http_router as identity_router,
    )
    from src.modules.queue.presentation.routers import (
        http_router as queue_router,
    )
    from src.modules.queue.presentation.routers import (
        ws_router as queue_ws_router,
    )
    from src.modules.telemetry.presentation.routers import (
        http_router as telemetry_router,
    )

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(auth_router)
    api_v1.include_router(identity_router)
    api_v1.include_router(queue_router)
    api_v1.include_router(consultation_router)
    api_v1.include_router(telemetry_router)
    app.include_router(api_v1)

    # 5. Real-time WebSocket signaling routers
    app.include_router(queue_ws_router)
    app.include_router(consultation_ws_router)

    return app


app = create_app()
