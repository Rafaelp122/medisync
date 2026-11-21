"""Unit tests for polymorphic environment settings and production invariants."""

import os
from collections.abc import Generator

import pytest
from pydantic import ValidationError
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
    assert settings.SIGNED_CACHE_BACKEND == "valkey"
    assert settings.CORS_ORIGINS == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


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
    assert settings.SIGNED_CACHE_BACKEND == "memory"
    assert settings.TELEMETRY_CACHE_BACKEND == "memory"
    assert settings.NOTIFICATION_PROVIDER == "fake"
    assert settings.POSTGRES_DB == "medisync"
    assert settings.CORS_ORIGINS == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_production_environment_fails_with_dev_secret_key() -> None:
    os.environ["ENVIRONMENT"] = "production"
    get_settings.cache_clear()

    dev_secret = "dev-insecure-secret-key-change-in-production-min-32-chars"
    with pytest.raises(ValidationError, match="SECRET_KEY insegura") as exc_info:
        ProductionSettings(
            SECRET_KEY=dev_secret,
            JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
            CORS_ORIGINS=["https://app.medisync.com.br"],
        )
    msg = exc_info.value.errors()[0]["msg"]
    assert f"len={len(dev_secret)}" in msg
    assert dev_secret not in msg


def test_production_environment_fails_with_short_secret_key() -> None:
    short_secret = "short-key"
    with pytest.raises(ValidationError, match="SECRET_KEY insegura") as exc_info:
        ProductionSettings(
            SECRET_KEY=short_secret,
            JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
            CORS_ORIGINS=["https://app.medisync.com.br"],
        )
    msg = exc_info.value.errors()[0]["msg"]
    assert f"len={len(short_secret)}" in msg
    assert short_secret not in msg


def test_production_environment_fails_with_dev_jwt_secret_key() -> None:
    dev_jwt = "dev-insecure-jwt-secret-key-change-in-production-min-32-chars"
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY insegura") as exc_info:
        ProductionSettings(
            SECRET_KEY="a-super-secret-app-key-with-sufficient-length-32-chars",
            JWT_SECRET_KEY=dev_jwt,
            CORS_ORIGINS=["https://app.medisync.com.br"],
        )
    msg = exc_info.value.errors()[0]["msg"]
    assert f"len={len(dev_jwt)}" in msg
    assert dev_jwt not in msg


def test_production_environment_fails_with_empty_or_wildcard_cors() -> None:
    with pytest.raises(ValueError, match=r"CORS_ORIGINS deve listar.*\[\]"):
        ProductionSettings(
            SECRET_KEY="a-super-secret-app-key-with-sufficient-length-32-chars",
            JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
            CORS_ORIGINS=[],
        )

    with pytest.raises(ValueError, match=r"CORS_ORIGINS deve listar.*\*"):
        ProductionSettings(
            SECRET_KEY="a-super-secret-app-key-with-sufficient-length-32-chars",
            JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
            CORS_ORIGINS=["*"],
        )


def test_production_environment_fails_with_fake_psc_provider() -> None:
    with pytest.raises(
        ValueError, match="PSC_DEFAULT_PROVIDER 'fake' não pode ser 'fake'"
    ):
        ProductionSettings(
            SECRET_KEY="a-super-secret-app-key-with-sufficient-length-32-chars",
            JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
            CORS_ORIGINS=["https://app.medisync.com.br"],
            PSC_DEFAULT_PROVIDER="fake",
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
    assert prod.SIGNED_CACHE_BACKEND == "valkey"
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


def test_settings_does_not_have_minio_attributes() -> None:
    """Valida que CommonSettings não possui atributos ou campos do MinIO (Issue #72)."""
    settings = CommonSettings()
    minio_keys = [k for k in CommonSettings.model_fields if k.startswith("MINIO_")]
    assert not minio_keys
    assert hasattr(settings, "MINIO_ROOT_USER") is False
    assert hasattr(settings, "MINIO_ENDPOINT") is False


def test_settings_loads_with_minio_env_vars_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valida que variáveis MINIO_* no ambiente são ignoradas sem erro (Issue #72)."""
    monkeypatch.setenv("MINIO_ROOT_USER", "test_user")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://test:9000")
    settings = CommonSettings()
    assert getattr(settings, "MINIO_ROOT_USER", None) is None


def test_production_environment_fails_with_sandbox_or_mock_liveness_provider() -> None:
    for provider in ("mock", "valkey_sandbox"):
        with pytest.raises(ValueError, match="LIVENESS_PROVIDER"):
            ProductionSettings(
                SECRET_KEY="a-super-secret-app-key-with-sufficient-length-32-chars",
                JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
                CORS_ORIGINS=["https://app.medisync.com.br"],
                LIVENESS_PROVIDER=provider,
            )


def test_production_environment_fails_with_localhost_webauthn_or_http_origin() -> None:
    with pytest.raises(ValueError, match="WEBAUTHN_RP_ID"):
        ProductionSettings(
            SECRET_KEY="a-super-secret-app-key-with-sufficient-length-32-chars",
            JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
            CORS_ORIGINS=["https://app.medisync.com.br"],
            WEBAUTHN_RP_ID="localhost",
        )
    with pytest.raises(
        ValueError, match=r"WEBAUTHN_ALLOWED_ORIGINS.*http://medisync\.app"
    ):
        ProductionSettings(
            SECRET_KEY="a-super-secret-app-key-with-sufficient-length-32-chars",
            JWT_SECRET_KEY="a-super-secret-jwt-key-with-sufficient-length-32-chars",
            CORS_ORIGINS=["https://app.medisync.com.br"],
            WEBAUTHN_ALLOWED_ORIGINS=["http://medisync.app"],
        )


def test_settings_removed_orphan_psc_and_s3_presigned_fields() -> None:
    """Dead config fields with zero readers must not exist in CommonSettings."""
    for field in (
        "S3_PRESIGNED_EXPIRATION_SECONDS",
        "PSC_CLIENT_ID",
        "PSC_CLIENT_SECRET",
    ):
        assert field not in CommonSettings.model_fields


def test_create_app_never_uses_wildcard_cors_even_under_debug_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CORSMiddleware must never receive allow_origins=['*'] with credentials=True."""
    from fastapi.middleware.cors import CORSMiddleware
    from src.main import create_app

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:5173", "*"]')
    get_settings.cache_clear()
    try:
        app = create_app()
        cors_mw = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
        allow_origins = cors_mw.kwargs.get("allow_origins")
        assert isinstance(allow_origins, list)
        assert "*" not in allow_origins
        assert "http://localhost:5173" in allow_origins
        assert cors_mw.kwargs.get("allow_credentials") is True
    finally:
        get_settings.cache_clear()
