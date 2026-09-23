from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fitness_bot.domain.enums import Goal, ProgramType, Sex
from fitness_bot.service.models.queries.base import Query, QueryResult


class GetNutritionQuery(Query):
    telegram_user_id: int
    subject_user_id: UUID | None = None


class GetNutritionQueryResult(QueryResult):
    """status: no_program | missing | stale | current."""

    status: str
    program_id: UUID | None = None
    program_type: ProgramType | None = None
    goal: Goal | None = None
    recommendation_id: UUID | None = None
    kcal: Decimal | None = None
    protein_g: Decimal | None = None
    fat_g: Decimal | None = None
    carb_g: Decimal | None = None
    calculation: str = ""
    meal_regularity: str = ""
    snapshot_sex: Sex | None = None
    snapshot_birth_year: int | None = None
    snapshot_height_cm: Decimal | None = None
    snapshot_weight_kg: Decimal | None = None
    snapshot_days_per_week: int | None = None
