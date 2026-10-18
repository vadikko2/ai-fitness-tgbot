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
        stored = self.guides.get(exercise_id)
        matched = next((item for item in self.exercises if item.id == exercise_id), None)
        if stored is None:
            if matched is None:
                return None
            return CatalogExerciseGuide(
                id=matched.id,
                name=matched.name,
                technique="",
                videos=(),
                primary_muscles=matched.primary_muscles,
                secondary_muscles=matched.secondary_muscles,
            )
        if matched is None or stored.primary_muscles or stored.secondary_muscles:
            return stored
        return CatalogExerciseGuide(
            id=stored.id,
            name=stored.name,
            technique=stored.technique,
            videos=stored.videos,
            primary_muscles=matched.primary_muscles,
            secondary_muscles=matched.secondary_muscles,
        )


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
    places: Sequence[str] = ("gym",),
) -> CatalogExerciseRecord:
    return CatalogExerciseRecord(
        id=exercise_id,
        name=name,
        primary_muscles=tuple(primary_muscles),
        secondary_muscles=tuple(secondary_muscles),
        places=tuple(places),
    )


def guide(
    *,
    exercise_id: UUID,
    name: str,
    technique: str,
    videos: Sequence[CatalogVideoLink] = (),
    primary_muscles: Sequence[str] = (),
    secondary_muscles: Sequence[str] = (),
) -> CatalogExerciseGuide:
    return CatalogExerciseGuide(
        id=exercise_id,
        name=name,
        technique=technique,
        videos=tuple(videos),
        primary_muscles=tuple(primary_muscles),
        secondary_muscles=tuple(secondary_muscles),
    )
