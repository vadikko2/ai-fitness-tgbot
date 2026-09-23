from __future__ import annotations

import cqrs

from fitness_bot.domain.catalog.match import match_exercises
from fitness_bot.service.models.queries.match_exercises import (
    ExerciseGuideVideoItem,
    GetExerciseGuideQuery,
    GetExerciseGuideResult,
    GetExerciseNamesQuery,
    GetExerciseNamesResult,
    MatchExerciseItem,
    MatchExercisesQuery,
    MatchExercisesResult,
)
from fitness_bot.service.ports.exercise_catalog import to_views
from fitness_bot.service.ports.video_search import ExerciseCatalogReader


class MatchExercisesQueryHandler(cqrs.RequestHandler[MatchExercisesQuery, MatchExercisesResult]):
    def __init__(self, catalog: ExerciseCatalogReader) -> None:
        self._catalog = catalog
        self._events: list[cqrs.Event] = []

    @property
    def events(self) -> list[cqrs.Event]:
        return list(self._events)

    async def handle(self, request: MatchExercisesQuery) -> MatchExercisesResult:
        records = await self._catalog.list_exercises()
        ranked = match_exercises(
            query=request.query,
            muscle=request.muscle,
            exercises=to_views(records),
            limit=request.limit,
        )
        return MatchExercisesResult(
            items=[
                MatchExerciseItem(exercise_id=item.exercise_id, name=item.name, score=item.score) for item in ranked
            ],
        )


class GetExerciseNamesQueryHandler(cqrs.RequestHandler[GetExerciseNamesQuery, GetExerciseNamesResult]):
    def __init__(self, catalog: ExerciseCatalogReader) -> None:
        self._catalog = catalog
        self._events: list[cqrs.Event] = []

    @property
    def events(self) -> list[cqrs.Event]:
        return list(self._events)

    async def handle(self, request: GetExerciseNamesQuery) -> GetExerciseNamesResult:
        _ = request
        records = await self._catalog.list_exercises()
        return GetExerciseNamesResult(
            names={str(record.id): record.name for record in records},
            primary_muscles={str(record.id): list(record.primary_muscles) for record in records},
        )


class GetExerciseGuideQueryHandler(cqrs.RequestHandler[GetExerciseGuideQuery, GetExerciseGuideResult]):
    def __init__(self, catalog: ExerciseCatalogReader) -> None:
        self._catalog = catalog
        self._events: list[cqrs.Event] = []

    @property
    def events(self) -> list[cqrs.Event]:
        return list(self._events)

    async def handle(self, request: GetExerciseGuideQuery) -> GetExerciseGuideResult:
        guide = await self._catalog.get_guide(request.exercise_id)
        if guide is None:
            return GetExerciseGuideResult(found=False)
        return GetExerciseGuideResult(
            found=True,
            exercise_id=guide.id,
            name=guide.name,
            technique=guide.technique,
            videos=[
                ExerciseGuideVideoItem(platform=video.platform, url=video.url, title=video.title)
                for video in guide.videos
            ],
        )
