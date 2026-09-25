from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fitness_bot.domain.enums import Goal, ProgramType, Sex
from fitness_bot.service.models.commands.base import Command, CommandResult


class GenerateNutritionCommand(Command):
    telegram_user_id: int
    subject_telegram_user_id: int | None = None
    subject_user_id: UUID | None = None
    force: bool = False


class GenerateNutritionCommandResult(CommandResult):
    recommendation_id: UUID | None = None
    agent_unavailable: bool = False
    schema_failed: bool = False
    already_current: bool = False
    reply: str = ""
    kcal: Decimal | None = None
    protein_g: Decimal | None = None
    fat_g: Decimal | None = None
    carb_g: Decimal | None = None
    calculation: str = ""
    meal_regularity: str = ""
    sports_nutrition: str = ""
    goal: Goal | None = None
    program_type: ProgramType | None = None
    snapshot_sex: Sex | None = None
    snapshot_birth_year: int | None = None
    snapshot_height_cm: Decimal | None = None
    snapshot_weight_kg: Decimal | None = None
    snapshot_days_per_week: int | None = None
    client_chat_id: int | None = None
    for_client: bool = False
