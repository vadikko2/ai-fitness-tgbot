from __future__ import annotations

from pathlib import Path

import cqrs

from fitness_bot.shared.paths import EXERCISES_JSONL_PATH, MUSCLE_GROUPS_PATH


class SeedExerciseCatalogCommand(cqrs.Request):
    """C2: build or refresh data/exercises.jsonl via LLM + video search APIs."""

    muscle_groups_path: Path = MUSCLE_GROUPS_PATH
    exercises_jsonl_path: Path = EXERCISES_JSONL_PATH
    max_videos_per_platform: int = 5


class SeedExerciseCatalogResult(cqrs.Response):
    muscle_groups: int
    exercises_written: int
    path: str
