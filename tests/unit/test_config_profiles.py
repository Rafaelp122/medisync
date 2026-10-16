"""Unit tests for polymorphic environment settings and production invariants."""

import os
from collections.abc import Generator

import pytest
from src.core.config import (
    CommonSettings,
    DevelopmentSettings,
    ProductionSettings,
    TestSettings,
    get_settings,
)


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Generator[None, None, None]:
    """Ensure get_settings cache and environment are reset between tests."""
    original_env = os.environ.get("ENVIRONMENT")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    if original_env is not None:
        os.environ["ENVIRONMENT"] = original_env
    else:
        os.environ.pop("ENVIRONMENT", None)


def test_default_environment_is_development() -> None:
    os.environ.pop("ENVIRONMENT", None)
    get_settings.cache_clear()
    settings = get_settings()

    assert isinstance(settings, DevelopmentSettings)
    assert settings.ENVIRONMENT == "development"
    assert settings.DEBUG is True
    assert settings.RATE_LIMIT_BACKEND == "valkey"
    assert settings.TOKEN_REVOCATION_BACKEND == "valkey"


def test_test_environment_settings() -> None:
    os.environ["ENVIRONMENT"] = "test"
    get_settings.cache_clear()
    settings = get_settings()

    assert isinstance(settings, TestSettings)
    assert settings.ENVIRONMENT == "test"
    assert settings.DEBUG is True
    assert settings.RATE_LIMIT_BACKEND == "memory"
    assert settings.TOKEN_REVOCATION_BACKEND == "memory"
    assert settings.VALIDATION_RATE_LIMIT_BACKEND == "memory"
    assert settings.TELEMETRY_CACHE_BACKEND == "memory"
    assert settings.NOTIFICATION_PROVIDER == "fake"
    assert settings.POSTGRES_DB == "medisync"


def test_production_environment_fails_with_dev_secret_key() -> None:
    os.environ["ENVIRONMENT"] = "production"
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="SECRET_KEY insegura"):
        ProductionSettings(
            SECRET_KEY="dev-insecure-secret-key-change-in-production-min-32-chars",
            JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
            CORS_ORIGINS=["https://app.medisync.com.br"],
        )


def test_production_environment_fails_with_short_secret_key() -> None:
    with pytest.raises(ValueError, match="SECRET_KEY insegura"):
        ProductionSettings(
            SECRET_KEY="short-key",
            JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
            CORS_ORIGINS=["https://app.medisync.com.br"],
        )


def test_production_environment_fails_with_dev_jwt_secret_key() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY insegura"):
        ProductionSettings(
            SECRET_KEY="a-super-secret-app-key-with-sufficient-length-32-chars",
            JWT_SECRET_KEY="dev-insecure-jwt-secret-key-change-in-production-min-32-chars",
            CORS_ORIGINS=["https://app.medisync.com.br"],
        )


def test_production_environment_fails_with_empty_cors() -> None:
    with pytest.raises(ValueError, match="CORS_ORIGINS deve listar"):
        ProductionSettings(
            SECRET_KEY="a-super-secret-app-key-with-sufficient-length-32-chars",
            JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
            CORS_ORIGINS=[],
        )


def test_production_environment_succeeds_with_valid_config() -> None:
    prod = ProductionSettings(
        SECRET_KEY="a-super-secret-app-key-with-sufficient-length-32-chars",
        JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
        CORS_ORIGINS=["https://app.medisync.com.br"],
    )

    assert prod.ENVIRONMENT == "production"
    assert prod.DEBUG is False
    assert prod.STORAGE_BACKEND == "s3"
    assert prod.RATE_LIMIT_BACKEND == "valkey"
    assert prod.TOKEN_REVOCATION_BACKEND == "valkey"
    assert prod.VALIDATION_RATE_LIMIT_BACKEND == "valkey"
    assert prod.TELEMETRY_CACHE_BACKEND == "valkey"


def test_database_url_computes_psycopg_schema() -> None:
    settings = CommonSettings(
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        POSTGRES_HOST="h",
        POSTGRES_PORT=5432,
        POSTGRES_DB="db",
        DATABASE_URL=None,
    )
    assert settings.async_database_url == "postgresql+psycopg://u:p@h:5432/db"

    override = CommonSettings(DATABASE_URL="postgresql://u:p@h:5432/custom_db")
    assert override.async_database_url == "postgresql+psycopg://u:p@h:5432/custom_db"
