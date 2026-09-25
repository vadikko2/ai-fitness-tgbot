from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.keyboards import back_to_menu_keyboard, home_keyboard, nutrition_no_program_keyboard
from fitness_bot.presentation.message_draft import (
    NUTRITION_WAITING_PHRASES,
    assistant_parse_failure_text,
    message_draft_scope,
)
from fitness_bot.service.models.commands.nutrition import GenerateNutritionCommand
from fitness_bot.service.models.queries.nutrition import GetNutritionQuery


def create_nutrition_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="nutrition")

    @router.callback_query(F.data == "nutr")
    async def handle_nutr(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        if callback.message is None:
            await callback.answer()
            return

        status = await mediator.send(GetNutritionQuery(telegram_user_id=callback.from_user.id))
        if status.status == "no_program":
            text = jinja_env.get_template("nutrition_no_program.j2").render()
            if callback.message:
                await callback.message.answer(text, reply_markup=nutrition_no_program_keyboard())
            await callback.answer()
            return

        if status.status == "current":
            text = jinja_env.get_template("nutrition.j2").render(
                reply="",
                kcal=status.kcal,
                protein_g=status.protein_g,
                fat_g=status.fat_g,
                carb_g=status.carb_g,
                calculation=status.calculation,
                meal_regularity=status.meal_regularity,
                sports_nutrition=status.sports_nutrition,
            )
            if callback.message:
                await callback.message.answer(text, reply_markup=back_to_menu_keyboard())
            await callback.answer()
            return

        # missing or stale → generate once
        await callback.answer()
        draft_preview = ""
        try:
            async with message_draft_scope(
                callback.bot,
                callback.message.chat.id,
                waiting_phrases=NUTRITION_WAITING_PHRASES,
            ) as draft:
                result = await mediator.send(GenerateNutritionCommand(telegram_user_id=callback.from_user.id))
                draft_preview = draft.preview_text
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось посчитать питание: {exc}")
            await callback.answer()
            return

        if result.agent_unavailable:
            if callback.message:
                await callback.message.answer(
                    jinja_env.get_template("agent_unavailable.j2").render(),
                    reply_markup=home_keyboard(),
                )
            await callback.answer()
            return
        if result.schema_failed or result.kcal is None:
            if callback.message:
                await callback.message.answer(
                    assistant_parse_failure_text(
                        result.reply or draft_preview,
                        hint="Не удалось разобрать ответ помощника. Попробуй ещё раз.",
                    ),
                    reply_markup=back_to_menu_keyboard(),
                )
            await callback.answer()
            return

        text = jinja_env.get_template("nutrition.j2").render(
            reply=result.reply,
            kcal=result.kcal,
            protein_g=result.protein_g,
            fat_g=result.fat_g,
            carb_g=result.carb_g,
            calculation=result.calculation,
            meal_regularity=result.meal_regularity,
            sports_nutrition=result.sports_nutrition,
        )
        if callback.message:
            await callback.message.answer(text, reply_markup=back_to_menu_keyboard())
        await callback.answer()

    return router
