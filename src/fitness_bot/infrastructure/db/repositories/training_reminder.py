from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fitness_bot.domain.workout.training_reminder import TrainingReminderPrefs
from fitness_bot.infrastructure.db.models import TrainingReminderRow
from fitness_bot.service.interfaces.uow import ITrainingReminderRepository


def training_reminder_to_domain(row: TrainingReminderRow) -> TrainingReminderPrefs:
    return TrainingReminderPrefs(
        user_id=row.user_id,
        evening_enabled=row.evening_enabled,
        morning_enabled=row.morning_enabled,
        last_evening_sent_on=row.last_evening_sent_on,
        last_morning_sent_on=row.last_morning_sent_on,
    )


def apply_training_reminder(row: TrainingReminderRow, prefs: TrainingReminderPrefs) -> None:
    row.evening_enabled = prefs.evening_enabled
    row.morning_enabled = prefs.morning_enabled
    row.last_evening_sent_on = prefs.last_evening_sent_on
    row.last_morning_sent_on = prefs.last_morning_sent_on


class SqlAlchemyTrainingReminderRepository(ITrainingReminderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> TrainingReminderPrefs | None:
        row = (
            await self._session.execute(select(TrainingReminderRow).where(TrainingReminderRow.user_id == user_id))
        ).scalar_one_or_none()
        return training_reminder_to_domain(row) if row else None

    async def save(self, prefs: TrainingReminderPrefs) -> TrainingReminderPrefs:
        row = (
            await self._session.execute(
                select(TrainingReminderRow).where(TrainingReminderRow.user_id == prefs.user_id),
            )
        ).scalar_one_or_none()
        if row is None:
            row = TrainingReminderRow(user_id=prefs.user_id)
            self._session.add(row)
        apply_training_reminder(row, prefs)
        await self._session.flush()
        return training_reminder_to_domain(row)

    async def list_all(self) -> list[TrainingReminderPrefs]:
        rows = (await self._session.execute(select(TrainingReminderRow))).scalars().all()
        return [training_reminder_to_domain(row) for row in rows]
