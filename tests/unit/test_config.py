"""Unit tests for application configuration and settings validation."""

import pytest
from pydantic import ValidationError
from src.core.config import ProductionSettings, Settings, get_settings


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


def test_multi_tenancy_defaults_to_enabled_without_default_tenant() -> None:
    """Multi-tenancy is enabled by default with no silent DEFAULT_TENANT_ID."""
    settings = Settings()
    assert settings.MULTI_TENANCY_ENABLED is True
    assert settings.DEFAULT_TENANT_ID is None


def test_single_tenant_mode_accepts_positive_default_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single-tenant mode succeeds when DEFAULT_TENANT_ID >= 1 is configured."""
    monkeypatch.setenv("MULTI_TENANCY_ENABLED", "false")
    monkeypatch.setenv("DEFAULT_TENANT_ID", "42")

    settings = Settings()
    assert settings.MULTI_TENANCY_ENABLED is False
    assert settings.DEFAULT_TENANT_ID == 42


@pytest.mark.parametrize("invalid_tenant_id", [None, 0, -1, -99])
def test_single_tenant_mode_rejects_missing_or_non_positive_default_tenant(
    invalid_tenant_id: int | None,
) -> None:
    """Single-tenant mode fails fast when DEFAULT_TENANT_ID is absent or <= 0."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            MULTI_TENANCY_ENABLED=False,
            DEFAULT_TENANT_ID=invalid_tenant_id,
        )
    msg = str(exc_info.value)
    assert str(invalid_tenant_id) in msg
    assert "MULTI_TENANCY_ENABLED=False" in msg


def test_multi_tenant_mode_rejects_default_tenant_id() -> None:
    """Multi-tenant mode forbids DEFAULT_TENANT_ID to prevent silent fallback."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(MULTI_TENANCY_ENABLED=True, DEFAULT_TENANT_ID=1)
    msg = str(exc_info.value)
    assert "1" in msg
    assert "MULTI_TENANCY_ENABLED=True" in msg


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
