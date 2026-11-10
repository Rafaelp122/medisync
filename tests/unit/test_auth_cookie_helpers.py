"""Unit tests for presentation cookie helpers (Issue #144)."""

from typing import TYPE_CHECKING

import pytest
from fastapi import Request, Response
from src.core.errors import ValidationError
from src.modules.auth.presentation.helpers import (
    clear_refresh_token_cookie,
    extract_refresh_token,
    resolve_cookie_secure,
    resolve_login_tenant_id,
    set_refresh_token_cookie,
)

if TYPE_CHECKING:
    from starlette.types import Scope


def test_set_refresh_token_cookie_sets_expected_attributes() -> None:
    response = Response()
    set_refresh_token_cookie(
        response,
        "test-refresh-token-xyz",
        max_age_days=7,
        secure=True,
    )

    set_cookie_header = response.headers.get("set-cookie")
    assert set_cookie_header is not None
    assert "refresh_token=test-refresh-token-xyz" in set_cookie_header
    assert "HttpOnly" in set_cookie_header
    assert (
        "SameSite=strict" in set_cookie_header
        or "samesite=strict" in set_cookie_header.lower()
    )
    assert (
        "Path=/api/v1/auth" in set_cookie_header
        or "path=/api/v1/auth" in set_cookie_header.lower()
    )
    assert (
        "Max-Age=604800" in set_cookie_header
        or "max-age=604800" in set_cookie_header.lower()
    )
    assert "Secure" in set_cookie_header or "secure" in set_cookie_header.lower()


def test_clear_refresh_token_cookie_deletes_cookie_with_matching_path() -> None:
    response = Response()
    clear_refresh_token_cookie(response, secure=True)

    set_cookie_header = response.headers.get("set-cookie")
    assert set_cookie_header is not None
    assert "refresh_token=" in set_cookie_header
    assert (
        "Path=/api/v1/auth" in set_cookie_header
        or "path=/api/v1/auth" in set_cookie_header.lower()
    )
    assert "Max-Age=0" in set_cookie_header or "max-age=0" in set_cookie_header.lower()


def test_extract_refresh_token_reads_cookie_when_body_is_empty() -> None:
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/refresh",
        "headers": [(b"cookie", b"refresh_token=cookie-token-123")],
    }
    request = Request(scope)

    token = extract_refresh_token(request, body_token=None)
    assert token == "cookie-token-123"

    token_empty = extract_refresh_token(request, body_token="  ")
    assert token_empty == "cookie-token-123"


def test_extract_refresh_token_respects_explicit_body_token() -> None:
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/refresh",
        "headers": [(b"cookie", b"refresh_token=cookie-token-123")],
    }
    request = Request(scope)

    token = extract_refresh_token(request, body_token="body-token-456")
    assert token == "body-token-456"


def test_extract_refresh_token_returns_none_when_both_missing() -> None:
    empty_headers: list[tuple[bytes, bytes]] = []
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/refresh",
        "headers": empty_headers,
    }
    request = Request(scope)

    token = extract_refresh_token(request, body_token=None)
    assert token is None

    token_empty = extract_refresh_token(request, body_token="   ")
    assert token_empty is None


def test_resolve_cookie_secure_respects_explicit_override() -> None:
    assert resolve_cookie_secure(None, secure=True) is True
    assert resolve_cookie_secure(None, secure=False) is False


def test_resolve_cookie_secure_respects_x_forwarded_proto() -> None:
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "scheme": "http",
        "headers": [(b"x-forwarded-proto", b"https")],
    }
    request = Request(scope)
    assert resolve_cookie_secure(request) is True


def test_resolve_cookie_secure_respects_https_scheme() -> None:
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "scheme": "https",
        "server": ("testserver", 443),
        "headers": [(b"host", b"testserver")],
    }
    request = Request(scope)
    assert resolve_cookie_secure(request) is True


def test_resolve_cookie_secure_returns_false_when_http_and_no_forwarded() -> None:
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "scheme": "http",
        "headers": [(b"x-forwarded-proto", b"http")],
    }
    request = Request(scope)
    assert resolve_cookie_secure(request) is False


def test_resolve_login_tenant_id_interpolates_offending_value() -> None:
    with pytest.raises(ValidationError) as exc_info:
        resolve_login_tenant_id(-5, 10)
    assert "'-5'" in exc_info.value.detail
    assert "esperado valor inteiro positivo" in exc_info.value.detail
