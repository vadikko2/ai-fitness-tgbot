from __future__ import annotations

from typing import Protocol


class LanguageModel(Protocol):
    async def complete(self, *, system: str, user: str) -> str:
        """Return model text for the given system and user prompts."""
