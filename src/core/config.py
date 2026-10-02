"""Application settings and environment configuration module."""

from functools import lru_cache
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings with environment variable loading and validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core Application ---
    APP_NAME: str = "MediSync Express"
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "dev-insecure-secret-key-change-in-production-min-32-chars"

    # --- Relational Database (PostgreSQL 17 / Psycopg 3) ---
    POSTGRES_USER: str = "medisync"
    POSTGRES_PASSWORD: str = "medisync"
    POSTGRES_DB: str = "medisync"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    # --- Database Connection Pool ---
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: float = 30.0
    DB_POOL_RECYCLE: int = 1800
    DB_ECHO: bool = False

    # --- Valkey 8.0 (Cache & Concurrency Queues) ---
    VALKEY_HOST: str = "localhost"
    VALKEY_PORT: int = 6379
    VALKEY_URL: str = "valkey://localhost:6379/0"
    VALKEY_MAX_CONNECTIONS: int = 50
    VALKEY_SOCKET_TIMEOUT: float = 5.0
    VALKEY_CONNECT_TIMEOUT: float = 5.0
    VALKEY_HEALTH_CHECK_INTERVAL: int = 30
    VALKEY_RETRY_ATTEMPTS: int = 3

    # --- LiveKit SFU (WebRTC Media Server) ---
    LIVEKIT_HOST: str = "localhost"
    LIVEKIT_PORT: int = 7880
    LIVEKIT_URL: str = "http://localhost:7880"
    LIVEKIT_API_KEY: str = "devkey"
    LIVEKIT_API_SECRET: str = "secret"

    # --- MinIO (S3-Compatible Document Storage) ---
    MINIO_ROOT_USER: str = "medisync"
    MINIO_ROOT_PASSWORD: str = "medisync123"
    MINIO_HOST: str = "localhost"
    MINIO_PORT: int = 9000
    MINIO_CONSOLE_PORT: int = 9001
    MINIO_ENDPOINT: str = "http://localhost:9000"
    MINIO_DEFAULT_BUCKET: str = "medisync-docs"
    MINIO_USE_SSL: bool = False

    @computed_field  # pyright: ignore[reportUntypedFunctionDecorator]
    @property
    def async_database_url(self) -> str:
        """Resolve the asynchronous PostgreSQL connection string using Psycopg 3."""
        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgresql+asyncpg://"):
                return self.DATABASE_URL.replace(
                    "postgresql+asyncpg://", "postgresql+psycopg://", 1
                )
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace(
                    "postgresql://", "postgresql+psycopg://", 1
                )
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # pyright: ignore[reportUntypedFunctionDecorator]
    @property
    def async_valkey_url(self) -> str:
        """Resolve the Valkey URL into a redis-py compatible URL scheme."""
        if self.VALKEY_URL.startswith("valkey://"):
            return self.VALKEY_URL.replace("valkey://", "redis://", 1)
        if self.VALKEY_URL.startswith("valkeys://"):
            return self.VALKEY_URL.replace("valkeys://", "rediss://", 1)
        return self.VALKEY_URL


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached singleton application settings instance."""
    return Settings()
