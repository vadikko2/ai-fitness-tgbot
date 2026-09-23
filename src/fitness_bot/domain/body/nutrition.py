from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fitness_bot.domain.enums import Goal, ProgramType, Sex
from fitness_bot.domain.errors import DomainError


class NutritionRecommendation(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    program_id: UUID
    goal: Goal
    stale: bool = False
    kcal: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carb_g: Decimal
    calculation: str
    meal_regularity: str
    snapshot_sex: Sex
    snapshot_birth_year: int
    snapshot_height_cm: Decimal
    snapshot_weight_kg: Decimal
    snapshot_days_per_week: int
    snapshot_program_type: ProgramType
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _invariants(self) -> NutritionRecommendation:
        if self.kcal <= 0:
            raise DomainError("kcal must be positive")
        if self.protein_g < 0 or self.fat_g < 0 or self.carb_g < 0:
            raise DomainError("macros must be non-negative")
        if self.snapshot_birth_year <= 0:
            raise DomainError("snapshot_birth_year must be positive")
        if self.snapshot_height_cm <= 0 or self.snapshot_weight_kg <= 0:
            raise DomainError("snapshot height and weight must be positive")
        if self.snapshot_days_per_week < 1 or self.snapshot_days_per_week > 7:
            raise DomainError("snapshot_days_per_week must be between 1 and 7")
        if not self.calculation.strip():
            raise DomainError("calculation must not be empty")
        if not self.meal_regularity.strip():
            raise DomainError("meal_regularity must not be empty")
        return self

    def mark_stale(self) -> None:
        self.stale = True

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        program_id: UUID,
        goal: Goal,
        kcal: Decimal,
        protein_g: Decimal,
        fat_g: Decimal,
        carb_g: Decimal,
        calculation: str,
        meal_regularity: str,
        snapshot_sex: Sex,
        snapshot_birth_year: int,
        snapshot_height_cm: Decimal,
        snapshot_weight_kg: Decimal,
        snapshot_days_per_week: int,
        snapshot_program_type: ProgramType,
    ) -> NutritionRecommendation:
        return cls(
            user_id=user_id,
            program_id=program_id,
            goal=goal,
            stale=False,
            kcal=kcal,
            protein_g=protein_g,
            fat_g=fat_g,
            carb_g=carb_g,
            calculation=calculation.strip(),
            meal_regularity=meal_regularity.strip(),
            snapshot_sex=snapshot_sex,
            snapshot_birth_year=snapshot_birth_year,
            snapshot_height_cm=snapshot_height_cm,
            snapshot_weight_kg=snapshot_weight_kg,
            snapshot_days_per_week=snapshot_days_per_week,
            snapshot_program_type=snapshot_program_type,
        )
