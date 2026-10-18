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
    """Gera hash criptográfico Argon2id para credencial de acesso (LGPD Art. 11).

    Regras: docs/explanation/architecture/security-and-authorization.md
    """
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verifica senha em texto plano contra hash Argon2id (LGPD Art. 11).

    Regras: docs/explanation/architecture/security-and-authorization.md
    """
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
    """Gera token provisório HMAC-SHA256 para sessão de acolhimento (US-01, ADR-001).

    Regras: docs/user-stories/US-01-acolhimento-triagem-tcle.md
    """
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
    """Valida e decodifica token provisório HMAC-SHA256 de acolhimento (US-01, ADR-001).

    Assegura integridade criptográfica e validade temporal no onboarding do paciente.
    Regras: docs/user-stories/US-01-acolhimento-triagem-tcle.md
    """
    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError(
            f"Token de acolhimento em formato inválido: possui {len(parts)} parte(s); "
            "esperadas exatamente 2 partes no formato 'payload.assinatura'."
        )

    payload_b64, sig_b64 = parts
    try:
        expected_sig = hmac.new(
            secret_key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
        ).digest()
        provided_sig = _b64url_decode(sig_b64)
    except Exception as exc:
        raise ValueError(
            f"Token de acolhimento adulterado ou inválido (sig={sig_b64[:8]}...): {exc}"
        ) from exc

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError(
            f"Assinatura do token de acolhimento inválida: "
            f"assinatura ('{sig_b64[:12]}...') não confere com segredo."
        )

    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        tam = len(payload_b64)
        raise ValueError(
            f"Payload do token de acolhimento malformado (len={tam}): {exc}"
        ) from exc

    if not isinstance(payload, dict):
        tipo_rec = type(payload).__name__
        raise ValueError(
            f"Payload do token de acolhimento inválido: tipo '{tipo_rec}'; "
            "esperado dicionário JSON com claims da sessão."
        )

    raw_dict: dict[object, object] = payload  # type: ignore[assignment]
    payload_dict: dict[str, Any] = {str(k): v for k, v in raw_dict.items()}

    exp = payload_dict.get("exp")
    if not isinstance(exp, (int, float)) or time.time() > exp:
        agora = int(time.time())
        raise ValueError(
            f"Token de acolhimento expirado: expiração={exp}; tempo atual={agora}."
        )

    return payload_dict
