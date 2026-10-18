from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.body.wellbeing import WELLBEING_FRESHNESS_WINDOW
from fitness_bot.domain.enums import SessionStatus
from fitness_bot.domain.errors import DomainError, NoFreshWellbeing
from fitness_bot.presentation.keyboards import (
    WELLBEING_HISTORY_PAGE_SIZE,
    home_keyboard,
    session_no_program_keyboard,
    wellbeing_history_keyboard,
    wellbeing_missing_keyboard,
    wellbeing_rest_day_keyboard,
)
from fitness_bot.presentation.message_draft import assistant_parse_failure_text, message_draft_scope
from fitness_bot.presentation.routers.program import render_proposal
from fitness_bot.presentation.routers.session import propose_wellbeing_session, propose_wellbeing_workout_edit
from fitness_bot.service.models.commands.program import AdaptWeekForWellbeingCommand
from fitness_bot.service.models.queries.body import GetWellbeingHistoryQuery
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery


def _freshness_hours() -> int:
    return int(WELLBEING_FRESHNESS_WINDOW.total_seconds() // 3600)


def create_wellbeing_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="wellbeing")

    async def _answer_missing(message: Message) -> None:
        text = jinja_env.get_template("wellbeing_missing.j2").render(freshness_hours=_freshness_hours())
        await message.answer(text, reply_markup=wellbeing_missing_keyboard())

    @router.callback_query(F.data.startswith("feel_hist"))
    async def handle_feel_hist(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        _, _, raw_offset = callback.data.partition(":")
        offset = int(raw_offset) if raw_offset.isdigit() else 0
        history = await mediator.send(
            GetWellbeingHistoryQuery(
                telegram_user_id=callback.from_user.id,
                offset=offset,
                limit=WELLBEING_HISTORY_PAGE_SIZE,
            ),
        )
        text = jinja_env.get_template("wellbeing_history.j2").render(items=history.items)
        if callback.message:
            await callback.message.answer(
                text,
                reply_markup=wellbeing_history_keyboard(
                    offset=history.offset,
                    has_more=history.has_more,
                    has_fresh_unapplied=history.has_fresh_unapplied,
                ),
            )
        await callback.answer()

    @router.callback_query(F.data.in_({"feel_adapt_today", "sess_feel_adapt"}))
    async def handle_feel_adapt_today(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        if not isinstance(callback.message, Message):
            await callback.answer()
            return
        await callback.answer()
        message = callback.message
        today = await mediator.send(GetTodayWorkoutQuery(telegram_user_id=callback.from_user.id))
        if today.screen == "no_program":
            text = jinja_env.get_template("session_no_program.j2").render()
            await message.answer(text, reply_markup=session_no_program_keyboard())
            return
        if not today.has_unapplied_wellbeing:
            await _answer_missing(message)
            return
        if today.screen == "rest":
            await message.answer(
                jinja_env.get_template("wellbeing_rest_day.j2").render(),
                reply_markup=wellbeing_rest_day_keyboard(),
            )
            return
        try:
            if today.screen == "session":
                if today.session_status != SessionStatus.IN_PROGRESS:
                    await message.answer(
                        "Тренировка уже завершается — самочувствие учту в следующей.",
                        reply_markup=home_keyboard(),
                    )
                    return
                await propose_wellbeing_workout_edit(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=message,
                    bot=callback.bot,
                    telegram_user_id=callback.from_user.id,
                )
                return
            await propose_wellbeing_session(
                jinja_env=jinja_env,
                mediator=mediator,
                message=message,
                bot=callback.bot,
                telegram_user_id=callback.from_user.id,
                offer_plain_start=True,
            )
        except NoFreshWellbeing:
            await _answer_missing(message)
        except DomainError as exc:
            await message.answer(f"Не удалось подстроить тренировку: {exc}")

    @router.callback_query(F.data == "feel_adapt_week")
    async def handle_feel_adapt_week(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        if not isinstance(callback.message, Message):
            await callback.answer()
            return
        await callback.answer()
        message = callback.message
        draft_preview = ""
        try:
            async with message_draft_scope(callback.bot, message.chat.id) as draft:
                result = await mediator.send(AdaptWeekForWellbeingCommand(telegram_user_id=callback.from_user.id))
                draft_preview = draft.preview_text
        except NoFreshWellbeing:
            await _answer_missing(message)
            return
        except DomainError as exc:
            await message.answer(f"Не удалось подстроить план недели: {exc}")
            return
        if result.agent_unavailable:
            await message.answer(jinja_env.get_template("agent_unavailable.j2").render(), reply_markup=home_keyboard())
            return
        if result.schema_failed or result.document is None:
            await message.answer(
                assistant_parse_failure_text(
                    result.reply or draft_preview,
                    hint="Не удалось разобрать ответ помощника. Попробуй ещё раз.",
                ),
            )
            return
        await render_proposal(
            jinja_env=jinja_env,
            mediator=mediator,
            message=message,
            reply=result.reply,
            document=result.document,
            telegram_user_id=callback.from_user.id,
        )

    return router
