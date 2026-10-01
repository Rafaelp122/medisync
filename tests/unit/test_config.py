"""Unit tests for application configuration and settings validation."""

import pytest
from pydantic import ValidationError
from src.core.config import Settings


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
