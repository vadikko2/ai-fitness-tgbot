from __future__ import annotations

from uuid import UUID

import cqrs


class MatchExercisesQuery(cqrs.Request):
    """Rank catalog exercises for an unresolved slot description."""

    query: str
    muscle: str | None = None
    limit: int = 5


class MatchExerciseItem(cqrs.Response):
    exercise_id: UUID
    name: str
    score: int


class MatchExercisesResult(cqrs.Response):
    items: list[MatchExerciseItem]


class GetExerciseNamesQuery(cqrs.Request):
    """Load catalog id → name map for workout rendering."""


class GetExerciseNamesResult(cqrs.Response):
    names: dict[str, str]
    primary_muscles: dict[str, list[str]] = {}


class GetExerciseGuideQuery(cqrs.Request):
    """Load catalog technique text and demo video links."""

    exercise_id: UUID


class ExerciseGuideVideoItem(cqrs.Response):
    platform: str
    url: str
    title: str


class GetExerciseGuideResult(cqrs.Response):
    found: bool = False
    exercise_id: UUID | None = None
    name: str = ""
    technique: str = ""
    videos: list[ExerciseGuideVideoItem] = []
