from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from fitness_bot.domain.catalog.match import CatalogExerciseView
from fitness_bot.service.ports.video_search import (
    CatalogExerciseGuide,
    CatalogExerciseRecord,
    CatalogVideoLink,
    ExerciseCatalogReader,
)


@dataclass
class InMemoryExerciseCatalog(ExerciseCatalogReader):
    exercises: list[CatalogExerciseRecord]
    guides: dict[UUID, CatalogExerciseGuide] = field(default_factory=dict)

    async def list_exercises(self) -> Sequence[CatalogExerciseRecord]:
        return tuple(self.exercises)

    async def get_guide(self, exercise_id: UUID) -> CatalogExerciseGuide | None:
        guide = self.guides.get(exercise_id)
        if guide is not None:
            return guide
        for exercise in self.exercises:
            if exercise.id == exercise_id:
                return CatalogExerciseGuide(
                    id=exercise.id,
                    name=exercise.name,
                    technique="",
                    videos=(),
                )
        return None


def to_views(records: Sequence[CatalogExerciseRecord]) -> list[CatalogExerciseView]:
    return [
        CatalogExerciseView(
            id=record.id,
            name=record.name,
            primary_muscles=record.primary_muscles,
            secondary_muscles=record.secondary_muscles,
        )
        for record in records
    ]


def record(
    *,
    exercise_id: UUID,
    name: str,
    primary_muscles: Sequence[str],
    secondary_muscles: Sequence[str] = (),
) -> CatalogExerciseRecord:
    return CatalogExerciseRecord(
        id=exercise_id,
        name=name,
        primary_muscles=tuple(primary_muscles),
        secondary_muscles=tuple(secondary_muscles),
    )


def guide(
    *,
    exercise_id: UUID,
    name: str,
    technique: str,
    videos: Sequence[CatalogVideoLink] = (),
) -> CatalogExerciseGuide:
    return CatalogExerciseGuide(
        id=exercise_id,
        name=name,
        technique=technique,
        videos=tuple(videos),
    )
