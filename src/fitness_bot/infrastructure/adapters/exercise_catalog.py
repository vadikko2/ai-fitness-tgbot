from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from fitness_bot.infrastructure.db.models import ExerciseRow
from fitness_bot.service.ports.video_search import (
    CatalogExerciseGuide,
    CatalogExerciseRecord,
    CatalogVideoLink,
    ExerciseCatalogReader,
)


class SqlAlchemyExerciseCatalog(ExerciseCatalogReader):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_exercises(self) -> Sequence[CatalogExerciseRecord]:
        async with self._session_factory() as session:
            result = await session.execute(select(ExerciseRow).options(selectinload(ExerciseRow.muscles)))
            rows = result.scalars().all()
            records: list[CatalogExerciseRecord] = []
            for row in rows:
                primary = tuple(m.muscle for m in row.muscles if m.role == "primary")
                secondary = tuple(m.muscle for m in row.muscles if m.role == "secondary")
                records.append(
                    CatalogExerciseRecord(
                        id=row.id,
                        name=row.name,
                        primary_muscles=primary,
                        secondary_muscles=secondary,
                    ),
                )
            return records

    async def get_guide(self, exercise_id: UUID) -> CatalogExerciseGuide | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ExerciseRow).where(ExerciseRow.id == exercise_id).options(selectinload(ExerciseRow.videos)),
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            videos = tuple(
                CatalogVideoLink(platform=video.platform, url=video.url, title=video.title)
                for video in sorted(row.videos, key=lambda item: item.position)
            )
            return CatalogExerciseGuide(
                id=row.id,
                name=row.name,
                technique=row.technique,
                videos=videos,
            )
