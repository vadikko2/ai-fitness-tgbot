"""Pack UUIDs into Telegram callback_data (64-byte limit)."""

from __future__ import annotations

import base64
from uuid import UUID

CALLBACK_DATA_LIMIT = 64


def pack_uuids(*values: UUID) -> str:
    raw = b"".join(value.bytes for value in values)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def unpack_uuids(token: str, count: int) -> tuple[UUID, ...]:
    padded = token + ("=" * (-len(token) % 4))
    raw = base64.urlsafe_b64decode(padded)
    expected = 16 * count
    if len(raw) != expected:
        raise ValueError(f"callback token length {len(raw)}, expected {expected}")
    return tuple(UUID(bytes=raw[index : index + 16]) for index in range(0, len(raw), 16))
