from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from fitness_bot.domain.enums import WeightSource
from fitness_bot.service.models.queries.base import Query, QueryResult


class WeightHistoryItem(QueryResult):
    id: UUID
    kilograms: Decimal
    measured_on: date
    source: WeightSource


class GetWeightHistoryQuery(Query):
    telegram_user_id: int
    limit: int = 30


class GetWeightHistoryQueryResult(QueryResult):
    items: list[WeightHistoryItem]
    latest_kg: Decimal | None


class GetWeightReminderQuery(Query):
    telegram_user_id: int


class GetWeightReminderQueryResult(QueryResult):
    local_time: time | None
    weekdays: list[int]


class MeasurementSiteItem(QueryResult):
    id: UUID
    code: str
    name: str
    is_custom: bool
    latest_cm: Decimal | None = None


class MeasurementHistoryItem(QueryResult):
    id: UUID
    site_id: UUID
    site_name: str
    centimeters: Decimal
    measured_at: datetime


class GetMeasurementHistoryQuery(Query):
    telegram_user_id: int
    site_id: UUID | None = None
    limit: int = 30


class GetMeasurementHistoryQueryResult(QueryResult):
    sites: list[MeasurementSiteItem]
    entries: list[MeasurementHistoryItem]


class GetMeasurementGuideQuery(Query):
    site_id: UUID


class GetMeasurementGuideQueryResult(QueryResult):
    site_id: UUID
    site_code: str
    site_name: str
    instruction: str | None


class DueWeightReminderItem(QueryResult):
    user_id: UUID
    telegram_user_id: int
    chat_id: int
    local_date: date
    local_time: time


class ListDueWeightRemindersQuery(Query):
    now: datetime | None = None


class ListDueWeightRemindersQueryResult(QueryResult):
    items: list[DueWeightReminderItem]
