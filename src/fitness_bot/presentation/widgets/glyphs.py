"""File ids of photos the companion transport has already sent."""

from __future__ import annotations

_COVERS: dict[str, str] = {}


def remember_glyph_cover(path: str, file_id: str) -> None:
    """Keep a Telegram file_id so a later video can use that photo as its cover."""
    _COVERS[path] = file_id


def glyph_cover_file_id(path: str | None) -> str | None:
    if path is None:
        return None
    return _COVERS.get(path)
