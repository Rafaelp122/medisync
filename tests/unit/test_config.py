"""Unit tests for application configuration and settings validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from src.core.config import ProductionSettings, Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_settings() -> None:
    """Validate default configuration values for local development."""
    settings = Settings(
        DATABASE_URL=None,
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_db",
        POSTGRES_HOST="127.0.0.1",
        POSTGRES_PORT=5432,
        DEBUG=False,
    )
    assert settings.ENVIRONMENT == "development"
    assert not settings.DEBUG
    assert (
        settings.async_database_url
        == "postgresql+psycopg://test_user:test_password@127.0.0.1:5432/test_db"
    )


def test_custom_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate that environment variables properly override defaults."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("DB_POOL_SIZE", "50")

    settings = Settings()
    assert settings.ENVIRONMENT == "production"
    assert settings.DEBUG is True
    assert settings.POSTGRES_PORT == 5433
    assert settings.DB_POOL_SIZE == 50


def test_database_url_normalization() -> None:
    """Validate normalization of standard postgresql:// or asyncpg:// to postgresql+psycopg://."""
    settings_asyncpg = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/mydb"
    )
    assert (
        settings_asyncpg.async_database_url
        == "postgresql+psycopg://user:pass@localhost:5432/mydb"
    )

    settings_standard = Settings(
        DATABASE_URL="postgresql://user:pass@localhost:5432/mydb"
    )
    assert (
        settings_standard.async_database_url
        == "postgresql+psycopg://user:pass@localhost:5432/mydb"
    )


def test_invalid_port_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate that invalid non-numeric port raises a ValidationError."""
    monkeypatch.setenv("POSTGRES_PORT", "invalid_port")
    with pytest.raises(ValidationError):
        Settings()


def test_config_sem_variaveis_multi_tenant() -> None:
    """Single-platform settings and .env.example must not define multi-tenant vars."""
    assert "MULTI_TENANCY_ENABLED" not in Settings.model_fields
    assert "DEFAULT_TENANT_ID" not in Settings.model_fields
    settings = Settings()
    assert not hasattr(settings, "MULTI_TENANCY_ENABLED")
    assert not hasattr(settings, "DEFAULT_TENANT_ID")

    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "VITE_TENANT_ID" not in env_example
    assert "MULTI_TENANCY_ENABLED" not in env_example
    assert "DEFAULT_TENANT_ID" not in env_example


def test_production_settings_rejects_debug_true() -> None:
    """Production profile must fail fast when DEBUG=True."""
    with pytest.raises(ValidationError, match="DEBUG=True"):
        ProductionSettings(
            DEBUG=True,
            SECRET_KEY="prod-secret-key-with-at-least-32-characters-long",
            JWT_SECRET_KEY="prod-jwt-secret-key-with-at-least-32-chars-long",
            CORS_ORIGINS=["https://medisync.app"],
        )


def test_get_settings_production_with_debug_true_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_settings() in production must reject DEBUG=true via ProductionSettings."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key-with-at-least-32-characters-long")
    monkeypatch.setenv(
        "JWT_SECRET_KEY", "prod-jwt-secret-key-with-at-least-32-chars-long"
    )
    monkeypatch.setenv("CORS_ORIGINS", '["https://medisync.app"]')
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError, match="DEBUG=True"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_common_settings_removed_dead_govbr_fields() -> None:
    """Dead Gov.br client/redirect fields must not exist in Settings."""
    assert "GOVBR_OIDC_ENABLED" in Settings.model_fields
    assert "GOVBR_CLIENT_ID" not in Settings.model_fields
    assert "GOVBR_REDIRECT_URI" not in Settings.model_fields
