"""MediSync Express — FastAPI Application Entrypoint."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from src.core.config import get_settings
from src.core.context import get_current_request_id, get_current_tenant_id
from src.core.database import engine
from src.core.dependencies import ValkeyDep
from src.core.errors import register_exception_handlers
from src.core.logging import setup_logging
from src.core.middleware import setup_middlewares
from src.core.schemas import HealthCheckResponse, ValkeyHealth
from src.core.valkey import (
    check_valkey_health,
    close_arq_pool,
    close_valkey_pool,
    get_valkey_pool,
)
from src.modules.queue.infrastructure.lua_loader import get_lua_script_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Lifespan context managing application startup and graceful shutdown."""
    logger = logging.getLogger("medisync.lifespan")

    # 1. Preload Lua scripts into Valkey on startup
    try:
        pool = get_valkey_pool()
        client = Redis(connection_pool=pool)
        try:
            script_manager = get_lua_script_manager()
            loaded = await script_manager.preload_scripts(client)
            logger.info(
                "Preloaded %d Valkey Lua scripts: %s", len(loaded), list(loaded.keys())
            )
        finally:
            await client.aclose()
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

    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
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
    @app.get("/healthz")
    async def healthcheck(
        valkey_client: ValkeyDep,
    ) -> HealthCheckResponse:
        valkey_telemetry: ValkeyHealth | None = None
        try:
            raw_health = await check_valkey_health(valkey_client)
            valkey_telemetry = ValkeyHealth(**raw_health)
        except Exception as exc:
            valkey_telemetry = ValkeyHealth(
                status="unhealthy", ping=False, error=str(exc)
            )

        return HealthCheckResponse(
            status="ok",
            version="0.1.0",
            tenant_id=get_current_tenant_id(),
            request_id=get_current_request_id(),
            valkey=valkey_telemetry,
        )

    from src.modules.auth.presentation.routers import auth_router
    from src.modules.consultation.presentation.routers import (
        consultation_router,
        doctor_ws_router,
        livekit_router,
        validation_router,
    )
    from src.modules.identity.presentation.routers import (
        onboarding_router,
        pacientes_router,
        patient_auth_router,
    )
    from src.modules.queue.presentation.routers import (
        admissao_router,
        alocacao_router,
        fila_router,
        queue_ws_router,
    )
    from src.modules.telemetry.presentation.routers import telemetry_router

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(auth_router)
    api_v1.include_router(patient_auth_router)
    api_v1.include_router(onboarding_router)
    api_v1.include_router(pacientes_router)
    api_v1.include_router(admissao_router)
    api_v1.include_router(alocacao_router)
    api_v1.include_router(fila_router)
    api_v1.include_router(livekit_router)
    api_v1.include_router(consultation_router)
    api_v1.include_router(validation_router)
    api_v1.include_router(telemetry_router)
    app.include_router(api_v1)

    # 5. Real-time WebSocket signaling routers
    app.include_router(queue_ws_router)
    app.include_router(doctor_ws_router)

    return app


app = create_app()
