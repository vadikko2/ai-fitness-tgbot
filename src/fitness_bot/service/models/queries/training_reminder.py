from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fitness_bot.service.models.queries.base import Query, QueryResult

TrainingReminderKind = Literal["evening", "morning"]


class GetTrainingReminderSettingsQuery(Query):
    telegram_user_id: int


class GetTrainingReminderSettingsQueryResult(QueryResult):
    evening_enabled: bool = True
    morning_enabled: bool = True


class DueTrainingReminderItem(QueryResult):
    user_id: UUID
    telegram_user_id: int
    chat_id: int
    kind: TrainingReminderKind
    target_date: date
    sent_on: date
    day_title: str
    weekday: int


class ListDueTrainingRemindersQuery(Query):
    now: datetime | None = None


class ListDueTrainingRemindersQueryResult(QueryResult):
    items: list[DueTrainingReminderItem]
