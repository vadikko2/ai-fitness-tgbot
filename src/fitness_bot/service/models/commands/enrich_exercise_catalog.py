from __future__ import annotations

from pathlib import Path

import cqrs

from fitness_bot.shared.paths import EXERCISES_JSONL_PATH


class EnrichExerciseCatalogCommand(cqrs.Request):
    """Rewrite technique + attach search-backed videos for existing JSONL rows."""

    exercises_jsonl_path: Path = EXERCISES_JSONL_PATH
    max_videos_per_platform: int = 5
    batch_size: int = 5
    only_short_technique: bool = False
    short_technique_chars: int = 120
    only_missing_videos: bool = False
    limit: int | None = None


class EnrichExerciseCatalogResult(cqrs.Response):
    exercises_processed: int
    exercises_updated: int
    path: str
