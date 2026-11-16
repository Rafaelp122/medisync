"""Pure FIDO2 / WebAuthn Level 3 cryptographic and CBOR helpers (US-14)."""

import base64
import binascii
import hashlib
import hmac
import json
import struct
from collections.abc import Sequence
from typing import Any, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from src.modules.auth.domain.exceptions import WebAuthnChallengeInvalidoError


def decode_b64url(raw: str) -> bytes | None:
    """Decode Base64url string into raw bytes, returning None on invalid input."""
    stripped = raw.strip()
    if not stripped:
        return None
    padded = stripped + "=" * (-len(stripped) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError, binascii.Error):
        return None


def encode_b64url(data: bytes) -> str:
    """Encode raw bytes into unpadded Base64url ASCII string."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def decode_and_validate_client_data(
    *,
    response: dict[str, object],
    expected_type: str,
    allowed_origins: Sequence[str],
) -> tuple[str, bytes]:
    """Decode WebAuthn clientDataJSON verifying type, origin and challenge.

    Regras: W3C WebAuthn Level 3 §7.1/§7.2, OWASP ASVS (ADR-005) e US-14.
    """
    raw_cdj = response.get("clientDataJSON")
    if not isinstance(raw_cdj, str) or not raw_cdj.strip():
        raise WebAuthnChallengeInvalidoError(
            "Payload WebAuthn com desafio divergente ou clientDataJSON ausente "
            "(esperado Base64url não vazio)."
        )

    stripped = raw_cdj.strip()
    raw_bytes = (
        stripped.encode("utf-8")
        if stripped.startswith("{")
        else decode_b64url(stripped)
    )
    if raw_bytes is None:
        raise WebAuthnChallengeInvalidoError(
            "clientDataJSON WebAuthn malformado (esperado Base64url ou JSON válido)."
        )

    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebAuthnChallengeInvalidoError(
            f"clientDataJSON WebAuthn não é JSON UTF-8 válido: {exc}."
        ) from exc

    if not isinstance(parsed, dict):
        raise WebAuthnChallengeInvalidoError(
            f"clientDataJSON WebAuthn inválido: recebido {type(parsed).__name__}, "
            "esperado objeto JSON."
        )

    parsed_dict = cast("dict[str, Any]", parsed)
    ceremony_type = parsed_dict.get("type")
    if ceremony_type != expected_type:
        raise WebAuthnChallengeInvalidoError(
            f"Campo 'type' inválido no clientDataJSON: recebido {ceremony_type!r}, "
            f"esperado '{expected_type}'."
        )

    origin = parsed_dict.get("origin")
    normalized_allowed = [item.rstrip("/") for item in allowed_origins]
    origin_clean = origin.rstrip("/") if isinstance(origin, str) else None
    if origin_clean is None or not any(
        hmac.compare_digest(origin_clean, allowed) for allowed in normalized_allowed
    ):
        raise WebAuthnChallengeInvalidoError(
            f"Campo 'origin' não autorizado no clientDataJSON: recebido {origin!r}, "
            f"esperados: {normalized_allowed}."
        )

    challenge = parsed_dict.get("challenge")
    if not isinstance(challenge, str) or not challenge.strip():
        raise WebAuthnChallengeInvalidoError(
            "Campo 'challenge' divergente ou ausente no clientDataJSON WebAuthn."
        )
    return challenge, raw_bytes


def _cbor_read_uint(data: bytes, offset: int, info: int) -> tuple[int, int]:
    if info < 24:
        return info, offset
    lengths = {24: (1, ">B"), 25: (2, ">H"), 26: (4, ">I"), 27: (8, ">Q")}
    spec = lengths.get(info)
    if spec is None or offset + spec[0] > len(data):
        raise ValueError(f"Cabeçalho CBOR inválido: info={info} em offset={offset}.")
    size, fmt = spec
    val = int(struct.unpack(fmt, data[offset : offset + size])[0])
    return val, offset + size


def _cbor_decode_item(data: bytes, offset: int) -> tuple[Any, int]:
    if offset >= len(data):
        raise ValueError(f"CBOR truncado em offset={offset} (len={len(data)}).")
    initial = data[offset]
    major = initial >> 5
    info = initial & 0x1F
    arg, pos = _cbor_read_uint(data, offset + 1, info)
    if major == 0:
        return arg, pos
    if major == 1:
        return -1 - arg, pos
    if major in (2, 3):
        end = pos + arg
        if end > len(data):
            raise ValueError(f"Slice CBOR fora dos limites: {end} > {len(data)}.")
        raw = data[pos:end]
        return (raw if major == 2 else raw.decode("utf-8")), end
    if major == 4:
        return _cbor_decode_array(data, pos, arg)
    if major == 5:
        return _cbor_decode_map(data, pos, arg)
    raise ValueError(f"Major type CBOR não suportado: {major}.")


def _cbor_decode_array(data: bytes, pos: int, count: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    for _ in range(count):
        item, pos = _cbor_decode_item(data, pos)
        items.append(item)
    return items, pos


def _cbor_decode_map(data: bytes, pos: int, count: int) -> tuple[dict[Any, Any], int]:
    mapping: dict[Any, Any] = {}
    for _ in range(count):
        key, pos = _cbor_decode_item(data, pos)
        val, pos = _cbor_decode_item(data, pos)
        mapping[key] = val
    return mapping, pos


def _cose_map_to_spki_b64url(cose_map: dict[Any, Any]) -> str:
    kty = cose_map.get(1)
    if kty == 2:
        x_bytes = cose_map.get(-2)
        y_bytes = cose_map.get(-3)
        if not isinstance(x_bytes, bytes) or not isinstance(y_bytes, bytes):
            raise ValueError(f"Coordenadas COSE EC inválidas: kty={kty}.")
        pub_nums = ec.EllipticCurvePublicNumbers(
            int.from_bytes(x_bytes, "big"),
            int.from_bytes(y_bytes, "big"),
            ec.SECP256R1(),
        )
        der = pub_nums.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return encode_b64url(der)
    if kty == 3:
        n_bytes = cose_map.get(-1)
        e_bytes = cose_map.get(-2)
        if not isinstance(n_bytes, bytes) or not isinstance(e_bytes, bytes):
            raise ValueError(f"Parâmetros COSE RSA inválidos: kty={kty}.")
        rsa_nums = rsa.RSAPublicNumbers(
            int.from_bytes(e_bytes, "big"),
            int.from_bytes(n_bytes, "big"),
        )
        der = rsa_nums.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return encode_b64url(der)
    raise ValueError(f"Tipo de chave COSE kty={kty!r} não suportado (esperado 2 ou 3).")


def _validate_auth_data_header(
    *,
    credential_id: str,
    auth_bytes: bytes,
    rp_id: str,
) -> int:
    rp_hash = auth_bytes[:32]
    expected_rp_hash = hashlib.sha256(rp_id.encode("utf-8")).digest()
    if not hmac.compare_digest(rp_hash, expected_rp_hash):
        raise WebAuthnChallengeInvalidoError(
            f"rpIdHash inválido no authenticatorData da credencial '{credential_id}'; "
            f"esperado hash SHA-256 de '{rp_id}'."
        )

    flags = auth_bytes[32]
    if not (flags & 0x01):
        raise WebAuthnChallengeInvalidoError(
            f"Flag User Present (UP) ausente no authenticatorData da credencial "
            f"'{credential_id}' (flags=0x{flags:02x}); esperado bit 0x01 ativo."
        )
    return int(struct.unpack(">I", auth_bytes[33:37])[0])


def extract_registration_key_and_count(
    *,
    credential_id: str,
    response: dict[str, object],
    rp_id: str,
) -> tuple[str, int]:
    """Extract validated SPKI key and initial sign_count from CBOR attestationObject.

    Regras: W3C WebAuthn Level 3 §7.1, ADR-005 e US-14.
    """
    raw_att = response.get("attestationObject")
    att_bytes = decode_b64url(raw_att) if isinstance(raw_att, str) else None
    if att_bytes is None:
        raise WebAuthnChallengeInvalidoError(
            f"attestationObject CBOR ausente ou inválido para a credencial "
            f"'{credential_id}'; registro FIDO2 exige attestationObject assinado."
        )
    try:
        att_map, _ = _cbor_decode_item(att_bytes, 0)
    except ValueError as exc:
        raise WebAuthnChallengeInvalidoError(
            f"attestationObject CBOR malformado para '{credential_id}': {exc}."
        ) from exc

    if not isinstance(att_map, dict):
        raise WebAuthnChallengeInvalidoError(
            f"attestationObject inválido para '{credential_id}'; esperado mapa CBOR."
        )
    auth_data = cast("dict[Any, Any]", att_map).get("authData")
    if not isinstance(auth_data, bytes) or len(auth_data) < 55:
        raise WebAuthnChallengeInvalidoError(
            f"authData ausente ou truncado no attestationObject de '{credential_id}'; "
            "esperado >= 55 bytes com attestedCredentialData."
        )

    sign_count = _validate_auth_data_header(
        credential_id=credential_id,
        auth_bytes=auth_data,
        rp_id=rp_id,
    )
    if not (auth_data[32] & 0x40):
        raise WebAuthnChallengeInvalidoError(
            f"Flag Attested Credential Data (AT) ausente em '{credential_id}'."
        )

    cred_id_len = int(struct.unpack(">H", auth_data[53:55])[0])
    cose_offset = 55 + cred_id_len
    if cose_offset >= len(auth_data):
        raise WebAuthnChallengeInvalidoError(
            f"COSE_Key ausente no authData de '{credential_id}'."
        )
    try:
        cose_map, _ = _cbor_decode_item(auth_data, cose_offset)
        if not isinstance(cose_map, dict):
            raise ValueError("COSE_Key deve ser um mapa CBOR.")
        spki_b64 = _cose_map_to_spki_b64url(cast("dict[Any, Any]", cose_map))
    except ValueError as exc:
        raise WebAuthnChallengeInvalidoError(
            f"Chave COSE WebAuthn inválida para '{credential_id}': {exc}."
        ) from exc
    return spki_b64, sign_count


def _verify_cryptographic_signature(
    passkey_id: str,
    public_key_b64: str,
    signature_bytes: bytes,
    signed_data: bytes,
) -> None:
    der_bytes = decode_b64url(public_key_b64)
    if der_bytes is None:
        raise WebAuthnChallengeInvalidoError(
            f"Chave pública armazenada para credencial '{passkey_id}' é inválida; "
            "esperado SPKI DER em Base64url."
        )
    try:
        pub_key = serialization.load_der_public_key(der_bytes)
        if isinstance(pub_key, ec.EllipticCurvePublicKey):
            pub_key.verify(signature_bytes, signed_data, ec.ECDSA(hashes.SHA256()))
            return
        if isinstance(pub_key, rsa.RSAPublicKey):
            pub_key.verify(
                signature_bytes,
                signed_data,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return
    except (InvalidSignature, ValueError) as exc:
        raise WebAuthnChallengeInvalidoError(
            f"Assinatura criptográfica WebAuthn inválida para credencial "
            f"'{passkey_id}'; esperado assinatura FIDO2 válida."
        ) from exc
    raise WebAuthnChallengeInvalidoError(
        f"Algoritmo de chave pública não suportado na credencial '{passkey_id}'."
    )


def verify_assertion_and_extract_sign_count(
    *,
    passkey_id: str,
    public_key_b64: str,
    current_sign_count: int,
    rp_id: str,
    response: dict[str, object],
    raw_cdj_bytes: bytes,
) -> int:
    """Validate authenticatorData flags, rpIdHash, sign_count and signature.

    Regras: W3C WebAuthn Level 3 §7.2, ADR-005 e US-14.
    """
    raw_auth = response.get("authenticatorData")
    raw_sig = response.get("signature")
    auth_bytes = decode_b64url(raw_auth) if isinstance(raw_auth, str) else None
    sig_bytes = decode_b64url(raw_sig) if isinstance(raw_sig, str) else None
    if auth_bytes is None or len(auth_bytes) < 37 or sig_bytes is None:
        raise WebAuthnChallengeInvalidoError(
            f"Assinatura ou authenticatorData ausente/malformado para credencial "
            f"'{passkey_id}'; esperado authenticatorData >= 37 bytes e signature."
        )

    novo_sign_count = _validate_auth_data_header(
        credential_id=passkey_id,
        auth_bytes=auth_bytes,
        rp_id=rp_id,
    )
    if current_sign_count > 0 and novo_sign_count <= current_sign_count:
        raise WebAuthnChallengeInvalidoError(
            f"Contador sign_count inválido para credencial '{passkey_id}': "
            f"recebido {novo_sign_count}, esperado > {current_sign_count} "
            "(suspeita de autenticador clonado)."
        )

    signed_data = auth_bytes + hashlib.sha256(raw_cdj_bytes).digest()
    _verify_cryptographic_signature(passkey_id, public_key_b64, sig_bytes, signed_data)
    return novo_sign_count
