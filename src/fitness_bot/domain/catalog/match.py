from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from fitness_bot.domain.catalog.normalize import tokenize


@dataclass(frozen=True, slots=True)
class CatalogExerciseView:
    id: UUID
    name: str
    primary_muscles: tuple[str, ...]
    secondary_muscles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    exercise_id: UUID
    name: str
    score: int


def _muscle_matches(exercise: CatalogExerciseView, muscle: str) -> bool:
    needle = muscle.casefold().strip()
    if not needle:
        return True
    muscles = (*(m.casefold() for m in exercise.primary_muscles), *(m.casefold() for m in exercise.secondary_muscles))
    return any(needle == m or needle in m or m in needle for m in muscles)


def _score(query_tokens: set[str], exercise: CatalogExerciseView) -> int:
    name_tokens = tokenize(exercise.name)
    muscle_tokens: set[str] = set()
    for muscle in (*exercise.primary_muscles, *exercise.secondary_muscles):
        muscle_tokens |= tokenize(muscle)
    name_overlap = len(query_tokens & name_tokens)
    muscle_overlap = len(query_tokens & muscle_tokens)
    return name_overlap * 3 + muscle_overlap


def match_exercises(
    *,
    query: str,
    muscle: str | None,
    exercises: Sequence[CatalogExerciseView],
    limit: int = 5,
) -> list[MatchCandidate]:
    """Rank catalog exercises for unresolved slots (plan MatchExercises algorithm)."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    def rank(pool: Sequence[CatalogExerciseView]) -> list[MatchCandidate]:
        scored: list[MatchCandidate] = []
        for exercise in pool:
            score = _score(query_tokens, exercise)
            if score <= 0:
                continue
            scored.append(MatchCandidate(exercise_id=exercise.id, name=exercise.name, score=score))
        scored.sort(key=lambda item: (-item.score, item.name.casefold()))
        return scored[:limit]

    if muscle and muscle.strip():
        filtered = [ex for ex in exercises if _muscle_matches(ex, muscle)]
        ranked = rank(filtered)
        if ranked:
            return ranked
        return rank(exercises)
    return rank(exercises)
