from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fitness_bot.infrastructure.db.repositories.body import (
    SqlAlchemyMeasurementRepository,
    SqlAlchemyProgressPhotoReminderRepository,
    SqlAlchemyProgressPhotoRepository,
    SqlAlchemyWeightReminderRepository,
    SqlAlchemyWeightRepository,
)
from fitness_bot.infrastructure.db.repositories.coach import SqlAlchemyCoachesRepository
from fitness_bot.infrastructure.db.repositories.feedback import SqlAlchemyFeedbackRepository
from fitness_bot.infrastructure.db.repositories.nutrition import SqlAlchemyNutritionRepository
from fitness_bot.infrastructure.db.repositories.program import (
    SqlAlchemyProgramsRepository,
    SqlAlchemyProposalsRepository,
)
from fitness_bot.infrastructure.db.repositories.session import SqlAlchemySessionsRepository
from fitness_bot.infrastructure.db.repositories.technique_video import SqlAlchemyTechniqueVideosRepository
from fitness_bot.infrastructure.db.repositories.users import SqlAlchemyUsersRepository
from fitness_bot.infrastructure.db.repositories.wellbeing import SqlAlchemyWellbeingRepository
from fitness_bot.service.interfaces.uow import IUow, IUowRepositories


def create_async_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    url = database_url
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    elif url.startswith("postgresql+psycopg://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql+psycopg://")
    engine = create_async_engine(url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


class SqlAlchemyUowRepositories(IUowRepositories):
    def __init__(self, session: AsyncSession) -> None:
        self._users = SqlAlchemyUsersRepository(session)
        self._weights = SqlAlchemyWeightRepository(session)
        self._weight_reminders = SqlAlchemyWeightReminderRepository(session)
        self._progress_photos = SqlAlchemyProgressPhotoRepository(session)
        self._progress_photo_reminders = SqlAlchemyProgressPhotoReminderRepository(session)
        self._measurements = SqlAlchemyMeasurementRepository(session)
        self._programs = SqlAlchemyProgramsRepository(session)
        self._proposals = SqlAlchemyProposalsRepository(session)
        self._sessions = SqlAlchemySessionsRepository(session)
        self._technique_videos = SqlAlchemyTechniqueVideosRepository(session)
        self._nutrition = SqlAlchemyNutritionRepository(session)
        self._wellbeing = SqlAlchemyWellbeingRepository(session)
        self._coaches = SqlAlchemyCoachesRepository(session)
        self._feedback = SqlAlchemyFeedbackRepository(session)

    @property
    def users(self) -> SqlAlchemyUsersRepository:
        return self._users

    @property
    def weights(self) -> SqlAlchemyWeightRepository:
        return self._weights

    @property
    def weight_reminders(self) -> SqlAlchemyWeightReminderRepository:
        return self._weight_reminders

    @property
    def progress_photos(self) -> SqlAlchemyProgressPhotoRepository:
        return self._progress_photos

    @property
    def progress_photo_reminders(self) -> SqlAlchemyProgressPhotoReminderRepository:
        return self._progress_photo_reminders

    @property
    def measurements(self) -> SqlAlchemyMeasurementRepository:
        return self._measurements

    @property
    def programs(self) -> SqlAlchemyProgramsRepository:
        return self._programs

    @property
    def proposals(self) -> SqlAlchemyProposalsRepository:
        return self._proposals

    @property
    def sessions(self) -> SqlAlchemySessionsRepository:
        return self._sessions

    @property
    def technique_videos(self) -> SqlAlchemyTechniqueVideosRepository:
        return self._technique_videos

    @property
    def nutrition(self) -> SqlAlchemyNutritionRepository:
        return self._nutrition

    @property
    def wellbeing(self) -> SqlAlchemyWellbeingRepository:
        return self._wellbeing

    @property
    def coaches(self) -> SqlAlchemyCoachesRepository:
        return self._coaches

    @property
    def feedback(self) -> SqlAlchemyFeedbackRepository:
        return self._feedback


class SqlAlchemyUow(IUow):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._committed = False

    @contextlib.asynccontextmanager
    async def _transaction(self) -> AsyncIterator[IUowRepositories]:
        self._committed = False
        self._session = self._session_factory()
        try:
            yield SqlAlchemyUowRepositories(self._session)
        except Exception:
            if self._session is not None:
                await self._session.rollback()
                await self._session.close()
                self._session = None
            raise

    async def _commit(self) -> None:
        if self._session is None:
            return
        await self._session.commit()
        self._committed = True
        await self._session.close()
        self._session = None

    async def _rollback(self) -> None:
        if self._session is None:
            return
        if not self._committed:
            await self._session.rollback()
        await self._session.close()
        self._session = None
