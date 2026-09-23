from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)


def normalize_exercise_name(name: str) -> str:
    """Collapse whitespace and casefold for upsert / unique lookup."""
    return " ".join(name.casefold().split())


def tokenize(text: str) -> set[str]:
    """Normalize free text into lowercase alphanumeric tokens (Latin + Cyrillic)."""
    return {match.group(0).casefold() for match in _TOKEN_RE.finditer(text)}
