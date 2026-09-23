from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fitness_bot.domain.enums import (
    ActivityLevel,
    ExpectedInput,
    ExperienceLevel,
    Goal,
    ProfileField,
    Sex,
)
from fitness_bot.service.models.queries.base import Query, QueryResult


class GetProfileQuery(Query):
    telegram_user_id: int
    now: datetime | None = None


class GetProfileQueryResult(QueryResult):
    user_id: UUID
    telegram_user_id: int
    chat_id: int
    sex: Sex | None
    birth_year: int | None
    age: int | None
    height_cm: Decimal | None
    weight_kg: Decimal | None
    experience: ExperienceLevel | None
    experience_details: str | None
    days_per_week: int | None
    training_weekdays: list[int]
    equipment: str | None
    limitations: str | None
    activity_level: ActivityLevel | None
    session_minutes: int | None
    body_fat_pct: Decimal | None
    body_fat_set: bool
    supplements: list[str] | None
    supplements_other: str | None
    diet_prefs: str | None
    pharma: str | None
    timezone_offset: str | None
    goal: Goal | None
    nutrition_stale: bool
    expected_input: ExpectedInput
    expected_field: str | None
    focus_slot: int | None
    profile_complete: bool
    next_field: ProfileField | None
    pending_site_id: UUID | None = None


class GetHomeQuery(Query):
    telegram_user_id: int
    now: datetime | None = None


class GetHomeQueryResult(QueryResult):
    user_id: UUID
    profile_complete: bool
    goal: Goal | None
    age: int | None
    weight_kg: Decimal | None
    is_moderator: bool = False
    coach_status: str | None = None
    active_clients_count: int = 0
    show_coach_badge: bool = False


class GetWorkflowQuery(Query):
    telegram_user_id: int


class GetWorkflowQueryResult(QueryResult):
    user_id: UUID
    chat_id: int
    expected_input: ExpectedInput
    expected_field: str | None
    focus_slot: int | None
    pending_site_id: UUID | None = None
    profile_complete: bool
    goal: Goal | None
