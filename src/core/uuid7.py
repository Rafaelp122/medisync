"""UUIDv7 generation conforming to RFC 9562."""

import os
import time
import uuid
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable


def uuid7() -> uuid.UUID:
    """Generate a UUIDv7 per RFC 9562.

    Uses native uuid.uuid7() if available (Python 3.14+), otherwise constructs
    the 128-bit structure using 48-bit millisecond timestamp and cryptographically
    secure random bytes.
    """
    native_fn = cast("Callable[[], uuid.UUID] | None", getattr(uuid, "uuid7", None))
    if native_fn is not None:
        return native_fn()

    timestamp_ms = int(time.time() * 1000)
    rand_bytes = os.urandom(10)

    b = bytearray(16)
    b[0:6] = timestamp_ms.to_bytes(6, byteorder="big")
    b[6] = 0x70 | (rand_bytes[0] & 0x0F)
    b[7] = rand_bytes[1]
    b[8] = 0x80 | (rand_bytes[2] & 0x3F)
    b[9:16] = rand_bytes[3:10]

    return uuid.UUID(bytes=bytes(b))


def uuid7_str() -> str:
    """Generate a UUIDv7 formatted as canonical hyphenated string."""
    return str(uuid7())


def is_valid_uuid(val: str) -> bool:
    """Validate whether a string is a valid UUID representation."""
    try:
        uuid.UUID(val)
        return True
    except (ValueError, AttributeError):
        return False
