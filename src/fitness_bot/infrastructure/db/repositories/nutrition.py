from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fitness_bot.domain.body.nutrition import NutritionRecommendation
from fitness_bot.domain.enums import Goal, ProgramType, Sex
from fitness_bot.infrastructure.db.models import NutritionRecommendationRow
from fitness_bot.service.interfaces.uow import INutritionRepository


def _to_domain(row: NutritionRecommendationRow) -> NutritionRecommendation:
    return NutritionRecommendation(
        id=row.id,
        user_id=row.user_id,
        program_id=row.program_id,
        goal=Goal(row.goal),
        stale=row.stale,
        kcal=row.kcal,
        protein_g=row.protein_g,
        fat_g=row.fat_g,
        carb_g=row.carb_g,
        calculation=row.calculation,
        meal_regularity=row.meal_regularity,
        sports_nutrition=row.sports_nutrition,
        snapshot_sex=Sex(row.snapshot_sex),
        snapshot_birth_year=row.snapshot_birth_year,
        snapshot_height_cm=row.snapshot_height_cm,
        snapshot_weight_kg=row.snapshot_weight_kg,
        snapshot_days_per_week=row.snapshot_days_per_week,
        snapshot_program_type=ProgramType(row.snapshot_program_type),
        created_at=row.created_at,
    )


class SqlAlchemyNutritionRepository(INutritionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_current(
        self,
        user_id: UUID,
        *,
        program_id: UUID,
        goal: Goal,
    ) -> NutritionRecommendation | None:
        result = await self._session.execute(
            select(NutritionRecommendationRow)
            .where(
                NutritionRecommendationRow.user_id == user_id,
                NutritionRecommendationRow.program_id == program_id,
                NutritionRecommendationRow.goal == goal.value,
                NutritionRecommendationRow.stale.is_(False),
            )
            .order_by(NutritionRecommendationRow.created_at.desc())
            .limit(1),
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def latest_for_user(self, user_id: UUID) -> NutritionRecommendation | None:
        result = await self._session.execute(
            select(NutritionRecommendationRow)
            .where(NutritionRecommendationRow.user_id == user_id)
            .order_by(NutritionRecommendationRow.created_at.desc())
            .limit(1),
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def mark_all_stale_for_user(self, user_id: UUID) -> None:
        await self._session.execute(
            update(NutritionRecommendationRow).where(NutritionRecommendationRow.user_id == user_id).values(stale=True),
        )

    async def add(self, recommendation: NutritionRecommendation) -> NutritionRecommendation:
        row = NutritionRecommendationRow(
            id=recommendation.id,
            user_id=recommendation.user_id,
            program_id=recommendation.program_id,
            goal=recommendation.goal.value,
            stale=recommendation.stale,
            kcal=recommendation.kcal,
            protein_g=recommendation.protein_g,
            fat_g=recommendation.fat_g,
            carb_g=recommendation.carb_g,
            calculation=recommendation.calculation,
            meal_regularity=recommendation.meal_regularity,
            sports_nutrition=recommendation.sports_nutrition,
            snapshot_sex=recommendation.snapshot_sex.value,
            snapshot_birth_year=recommendation.snapshot_birth_year,
            snapshot_height_cm=recommendation.snapshot_height_cm,
            snapshot_weight_kg=recommendation.snapshot_weight_kg,
            snapshot_days_per_week=recommendation.snapshot_days_per_week,
            snapshot_program_type=recommendation.snapshot_program_type.value,
            created_at=recommendation.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def save(self, recommendation: NutritionRecommendation) -> NutritionRecommendation:
        result = await self._session.execute(
            select(NutritionRecommendationRow).where(NutritionRecommendationRow.id == recommendation.id),
        )
        row = result.scalar_one()
        row.stale = recommendation.stale
        row.kcal = recommendation.kcal
        row.protein_g = recommendation.protein_g
        row.fat_g = recommendation.fat_g
        row.carb_g = recommendation.carb_g
        row.calculation = recommendation.calculation
        row.meal_regularity = recommendation.meal_regularity
        row.sports_nutrition = recommendation.sports_nutrition
        await self._session.flush()
        return _to_domain(row)
