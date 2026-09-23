from __future__ import annotations

import cqrs

from fitness_bot.domain.body.nutrition import NutritionRecommendation
from fitness_bot.domain.enums import Goal, ProgramType
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User
from fitness_bot.service.authz import require_coach_of
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.queries import nutrition as queries


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


def _result(
    status: str,
    *,
    program_id=None,
    program_type: ProgramType | None = None,
    goal: Goal | None = None,
    recommendation: NutritionRecommendation | None = None,
) -> queries.GetNutritionQueryResult:
    return queries.GetNutritionQueryResult(
        status=status,
        program_id=program_id,
        program_type=program_type,
        goal=goal,
        recommendation_id=recommendation.id if recommendation is not None else None,
        kcal=recommendation.kcal if recommendation is not None else None,
        protein_g=recommendation.protein_g if recommendation is not None else None,
        fat_g=recommendation.fat_g if recommendation is not None else None,
        carb_g=recommendation.carb_g if recommendation is not None else None,
        calculation=recommendation.calculation if recommendation is not None else "",
        meal_regularity=recommendation.meal_regularity if recommendation is not None else "",
        snapshot_sex=recommendation.snapshot_sex if recommendation is not None else None,
        snapshot_birth_year=recommendation.snapshot_birth_year if recommendation is not None else None,
        snapshot_height_cm=recommendation.snapshot_height_cm if recommendation is not None else None,
        snapshot_weight_kg=recommendation.snapshot_weight_kg if recommendation is not None else None,
        snapshot_days_per_week=recommendation.snapshot_days_per_week if recommendation is not None else None,
    )


class GetNutritionQueryHandler(cqrs.RequestHandler[queries.GetNutritionQuery, queries.GetNutritionQueryResult]):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetNutritionQuery) -> queries.GetNutritionQueryResult:
        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if request.subject_user_id is not None:
                await require_coach_of(repos, actor, request.subject_user_id)
                user = _require_user(await repos.users.get_by_id(request.subject_user_id))
            else:
                user = actor
            if user.active_program_id is None or user.goal is None:
                return _result("no_program", goal=user.goal)

            program = await repos.programs.get_by_id(user.active_program_id)
            if program is None:
                return _result("no_program", goal=user.goal)

            current = await repos.nutrition.get_current(
                user.id,
                program_id=program.id,
                goal=user.goal,
            )
            if current is not None and not user.nutrition_stale:
                return _result(
                    "current",
                    program_id=program.id,
                    program_type=program.program_type,
                    goal=user.goal,
                    recommendation=current,
                )

            latest = await repos.nutrition.latest_for_user(user.id)
            status = "stale" if latest is not None or user.nutrition_stale else "missing"
            return _result(
                status,
                program_id=program.id,
                program_type=program.program_type,
                goal=user.goal,
                recommendation=latest,
            )
