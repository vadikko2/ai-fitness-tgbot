from __future__ import annotations

from typing import Protocol


class SpeechToText(Protocol):
    async def transcribe(self, *, audio: bytes, content_type: str) -> str:
        """Return transcript text for an audio payload."""
