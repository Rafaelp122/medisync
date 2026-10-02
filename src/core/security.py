import base64
import hashlib
import hmac
import json
import time
from typing import Any
from uuid import UUID

from pwdlib import PasswordHash

# Initialize PasswordHash with recommended Argon2id configuration
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Generate an Argon2id cryptographic hash for the given plain text password."""
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify whether a plain text password matches an Argon2id hash."""
    if not hashed_password:
        return False
    try:
        return _password_hash.verify(password, hashed_password)
    except Exception:
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + padding).encode("utf-8"))


def create_intake_token(
    paciente_id: UUID,
    organizacao_id: int,
    secret_key: str,
    expires_in_seconds: int = 7200,
) -> str:
    """Generate a tamper-proof HMAC-SHA256 provisional intake token for onboarding."""
    now = int(time.time())
    payload = {
        "paciente_id": str(paciente_id),
        "organizacao_id": organizacao_id,
        "tipo": "intake_provisional",
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    payload_b64 = _b64url_encode(payload_json)

    signature = hmac.new(
        secret_key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
    ).digest()
    sig_b64 = _b64url_encode(signature)

    return f"{payload_b64}.{sig_b64}"


def verify_intake_token(token: str, secret_key: str) -> dict[str, Any]:
    """Verify and decode a provisional intake token.

    Raises:
        ValueError: If token signature is invalid, payload is malformed or expired.
    """
    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("Token de acolhimento em formato inválido.")

    payload_b64, sig_b64 = parts
    try:
        expected_sig = hmac.new(
            secret_key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
        ).digest()
        provided_sig = _b64url_decode(sig_b64)
    except Exception as exc:
        raise ValueError("Token de acolhimento adulterado ou inválido.") from exc

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError("Assinatura do token de acolhimento inválida.")

    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Payload do token de acolhimento malformado.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Payload do token de acolhimento inválido.")

    raw_dict: dict[object, object] = payload  # type: ignore[assignment]
    payload_dict: dict[str, Any] = {str(k): v for k, v in raw_dict.items()}

    exp = payload_dict.get("exp")
    if not isinstance(exp, (int, float)) or time.time() > exp:
        raise ValueError("Token de acolhimento expirado.")

    return payload_dict
