from __future__ import annotations

from typing import Protocol


class ObjectStorage(Protocol):
    async def put(self, key: str, body: bytes, content_type: str) -> None:
        """Store an object under key."""

    async def get(self, key: str) -> bytes:
        """Read object bytes by key."""

    async def delete(self, key: str) -> None:
        """Delete object by key."""
