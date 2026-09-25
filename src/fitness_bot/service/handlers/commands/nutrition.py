from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import cqrs

from fitness_bot.domain.body.nutrition import NutritionRecommendation
from fitness_bot.domain.enums import ProgramType
from fitness_bot.domain.errors import AgentUnavailable, DomainError, InvalidWorkoutDocument
from fitness_bot.domain.users.user import User
from fitness_bot.service.authz import require_coach_of
from fitness_bot.service.handlers.commands.agent_json import clip_reply, complete_json
from fitness_bot.service.handlers.commands.program import build_profile_payload
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.commands import nutrition as cmds
from fitness_bot.service.ports.language_model import LanguageModel

# Align with nutrition_advisor.md limits (above the global 500-char coach reply default).
_NUTRITION_REPLY_MAX = 1200
_NUTRITION_PROSE_MAX = 800


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


def _clip_stored(text: object) -> str:
    return clip_reply(text, max_chars=_NUTRITION_PROSE_MAX)


def _parse_decimal(value: object, *, name: str) -> Decimal:
    if value is None or value == "":
        raise InvalidWorkoutDocument(f"{name} is required")
    return Decimal(str(value))


def _nutrition_from_payload(
    payload: dict[str, Any],
    *,
    user: User,
    program_id: Any,
    program_type: ProgramType,
    weight_kg: Decimal,
) -> tuple[NutritionRecommendation, str]:
    if user.sex is None or user.birth_year is None or user.height_cm is None:
        raise DomainError("profile must include sex, birth_year, and height for nutrition")
    if user.days_per_week is None or user.goal is None:
        raise DomainError("profile must include days_per_week and goal for nutrition")
    recommendation = NutritionRecommendation.create(
        user_id=user.id,
        program_id=program_id,
        goal=user.goal,
        kcal=_parse_decimal(payload.get("kcal"), name="kcal"),
        protein_g=_parse_decimal(payload.get("protein_g"), name="protein_g"),
        fat_g=_parse_decimal(payload.get("fat_g"), name="fat_g"),
        carb_g=_parse_decimal(payload.get("carb_g"), name="carb_g"),
        calculation=_clip_stored(payload.get("calculation")),
        meal_regularity=_clip_stored(payload.get("meal_regularity")),
        sports_nutrition=_clip_stored(payload.get("sports_nutrition")),
        snapshot_sex=user.sex,
        snapshot_birth_year=user.birth_year,
        snapshot_height_cm=user.height_cm,
        snapshot_weight_kg=weight_kg,
        snapshot_days_per_week=user.days_per_week,
        snapshot_program_type=program_type,
    )
    return recommendation, clip_reply(payload.get("reply"), max_chars=_NUTRITION_REPLY_MAX)


class GenerateNutritionCommandHandler(
    cqrs.RequestHandler[cmds.GenerateNutritionCommand, cmds.GenerateNutritionCommandResult],
):
    def __init__(self, uow: IUow, language_model: LanguageModel) -> None:
        self._uow = uow
        self._language_model = language_model

    async def handle(self, request: cmds.GenerateNutritionCommand) -> cmds.GenerateNutritionCommandResult:
        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            for_client = False
            client_chat_id = None
            if request.subject_user_id is not None or request.subject_telegram_user_id is not None:
                if request.subject_user_id is not None:
                    user = _require_user(await repos.users.get_by_id(request.subject_user_id))
                else:
                    user = _require_user(
                        await repos.users.get_by_telegram_id(request.subject_telegram_user_id),  # type: ignore[arg-type]
                    )
                await require_coach_of(repos, actor, user.id)
                for_client = True
                client_chat_id = user.chat_id
            else:
                user = actor
            if user.active_program_id is None:
                raise DomainError("active program is required for nutrition")
            if user.goal is None:
                raise DomainError("goal is required for nutrition")
            program = await repos.programs.get_by_id(user.active_program_id)
            if program is None:
                raise DomainError("active program not found")

            current = await repos.nutrition.get_current(
                user.id,
                program_id=program.id,
                goal=user.goal,
            )
            if current is not None and not user.nutrition_stale:
                return cmds.GenerateNutritionCommandResult(
                    recommendation_id=current.id,
                    already_current=True,
                    kcal=current.kcal,
                    protein_g=current.protein_g,
                    fat_g=current.fat_g,
                    carb_g=current.carb_g,
                    calculation=current.calculation,
                    meal_regularity=current.meal_regularity,
                    sports_nutrition=current.sports_nutrition,
                    goal=current.goal,
                    program_type=current.snapshot_program_type,
                    snapshot_sex=current.snapshot_sex,
                    snapshot_birth_year=current.snapshot_birth_year,
                    snapshot_height_cm=current.snapshot_height_cm,
                    snapshot_weight_kg=current.snapshot_weight_kg,
                    snapshot_days_per_week=current.snapshot_days_per_week,
                    client_chat_id=client_chat_id,
                    for_client=for_client,
                )

            weight = await repos.weights.latest_for_user(user.id)
            if weight is None:
                raise DomainError("weight is required for nutrition")

            history = await repos.sessions.list_completed_for_user(user.id, limit=10)
            program_json = json.dumps(
                {
                    "id": str(program.id),
                    "program_type": program.program_type.value,
                    "days": [
                        {
                            "weekday": day.weekday,
                            "title": day.title,
                            "position": day.position,
                            "intensity": day.intensity.value,
                            "training_style": day.training_style.value,
                            "slot_count": len(day.slots),
                            "planned_sets": sum(slot.sets for slot in day.slots),
                        }
                        for day in program.days
                    ],
                },
                ensure_ascii=False,
            )
            history_json = json.dumps(
                [
                    {
                        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                        "title": session.day.title,
                        "intensity": session.day.intensity.value,
                        "training_style": session.day.training_style.value,
                        "slot_count": len(session.day.slots),
                        "planned_sets": sum(slot.sets for slot in session.day.slots),
                        "logged_slots": sum(1 for slot in session.day.slots if slot.actual is not None),
                    }
                    for session in history
                ],
                ensure_ascii=False,
            )

            try:
                payload = await complete_json(
                    self._language_model,
                    prompt_name="nutrition_advisor.md",
                    prompt_context={
                        "profile_json": json.dumps(
                            await build_profile_payload(repos, user, weight_kg=weight.kilograms),
                            ensure_ascii=False,
                        ),
                        "goal": user.goal.value,
                        "program_json": program_json,
                        "history_json": history_json,
                        "weight_kg": str(weight.kilograms),
                    },
                )
            except AgentUnavailable:
                return cmds.GenerateNutritionCommandResult(agent_unavailable=True)

            try:
                recommendation, reply = _nutrition_from_payload(
                    payload,
                    user=user,
                    program_id=program.id,
                    program_type=program.program_type,
                    weight_kg=weight.kilograms,
                )
            except (InvalidWorkoutDocument, DomainError, ValueError, TypeError, KeyError):
                return cmds.GenerateNutritionCommandResult(
                    schema_failed=True,
                    reply=clip_reply(
                        payload.get("reply") if isinstance(payload, dict) else None,
                        max_chars=_NUTRITION_REPLY_MAX,
                    ),
                )

            await repos.nutrition.mark_all_stale_for_user(user.id)
            saved = await repos.nutrition.add(recommendation)
            user.nutrition_stale = False
            await repos.users.save(user)
            return cmds.GenerateNutritionCommandResult(
                recommendation_id=saved.id,
                reply=reply,
                kcal=saved.kcal,
                protein_g=saved.protein_g,
                fat_g=saved.fat_g,
                carb_g=saved.carb_g,
                calculation=saved.calculation,
                meal_regularity=saved.meal_regularity,
                sports_nutrition=saved.sports_nutrition,
                goal=saved.goal,
                program_type=saved.snapshot_program_type,
                snapshot_sex=saved.snapshot_sex,
                snapshot_birth_year=saved.snapshot_birth_year,
                snapshot_height_cm=saved.snapshot_height_cm,
                snapshot_weight_kg=saved.snapshot_weight_kg,
                snapshot_days_per_week=saved.snapshot_days_per_week,
                client_chat_id=client_chat_id,
                for_client=for_client,
            )
