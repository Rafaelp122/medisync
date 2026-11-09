"""RFC 6238 Time-Based One-Time Password (TOTP) pure Python implementation.

Regras: ADR-007 (MFA), RF-01 e docs/explanation/domains/auth-domain.md.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def _pad_base32(secret: str) -> str:
    """Ajusta padding Base32 para decodificação segura."""
    clean = secret.strip().upper().replace(" ", "")
    missing_padding = len(clean) % 8
    if missing_padding != 0:
        clean += "=" * (8 - missing_padding)
    return clean


def generate_totp_secret(num_bytes: int = 20) -> str:
    """Gera chave secreta criptograficamente segura codificada em Base32.

    Regras: ADR-007, RF-01 e docs/explanation/domains/auth-domain.md.
    """
    raw_bytes = secrets.token_bytes(num_bytes)
    return base64.b32encode(raw_bytes).decode("utf-8").replace("=", "")


def generate_totp_code(
    secret_b32: str,
    timestamp: int | None = None,
    *,
    digits: int = 6,
    interval: int = 30,
) -> str:
    """Calcula código numérico TOTP sob RFC 6238 / RFC 4226 com HMAC-SHA1.

    Regras: ADR-007, RF-01 e docs/explanation/domains/auth-domain.md.
    """
    padded = _pad_base32(secret_b32)
    key = base64.b32decode(padded, casefold=True)
    ts = int(time.time()) if timestamp is None else timestamp
    counter = ts // interval
    counter_bytes = struct.pack(">Q", counter)

    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    token = binary % (10**digits)
    return f"{token:0{digits}d}"


def verify_totp_code(
    secret_b32: str,
    code: str,
    *,
    window: int = 1,
    interval: int = 30,
    timestamp: int | None = None,
) -> bool:
    """Valida código TOTP com tolerância temporal contra clock drift em tempo constante.

    Regras: ADR-007, RF-01 e docs/explanation/domains/auth-domain.md.
    """
    clean_code = code.strip()
    if len(clean_code) != 6 or not clean_code.isdigit():
        return False

    base_time = int(time.time()) if timestamp is None else timestamp
    for offset in range(-window, window + 1):
        test_time = base_time + (offset * interval)
        expected = generate_totp_code(
            secret_b32, timestamp=test_time, digits=6, interval=interval
        )
        if hmac.compare_digest(expected, clean_code):
            return True

    return False


def build_totp_uri(
    secret_b32: str,
    account_name: str,
    issuer: str = "MediSync",
) -> str:
    """Gera URI otpauth:// padrão para escaneamento via QR Code por autenticadores.

    Regras: ADR-007, RF-01 e docs/explanation/domains/auth-domain.md.
    """
    safe_account = quote(account_name)
    safe_issuer = quote(issuer)
    return (
        f"otpauth://totp/{safe_issuer}:{safe_account}"
        f"?secret={secret_b32}&issuer={safe_issuer}&algorithm=SHA1&digits=6&period=30"
    )
