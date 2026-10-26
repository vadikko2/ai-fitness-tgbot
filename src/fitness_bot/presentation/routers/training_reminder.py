from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.keyboards import WEEKDAY_LABELS, back_to_menu_keyboard, profile_reminders_keyboard
from fitness_bot.presentation.message_draft import message_draft_scope
from fitness_bot.presentation.routers.session import render_next_session_proposal
from fitness_bot.service.models.commands.session import GenerateNextSessionCommand
from fitness_bot.service.models.commands.training_reminder import SkipTrainingDayCommand, ToggleTrainingReminderCommand
from fitness_bot.service.models.queries.training_reminder import GetTrainingReminderSettingsQuery

_KEEP_PLAN = "Не получилось подготовить черновик — план остаётся как есть."


def create_training_reminder_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="training_reminder")

    async def _answer(callback: CallbackQuery, text: str, **kwargs) -> None:
        if callback.message:
            await callback.message.answer(text, reply_markup=kwargs.get("reply_markup"))
        await callback.answer()

    async def _show_settings(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        settings = await mediator.send(GetTrainingReminderSettingsQuery(telegram_user_id=callback.from_user.id))
        await _answer(
            callback,
            jinja_env.get_template("training_reminder_settings.j2").render(),
            reply_markup=profile_reminders_keyboard(
                evening_enabled=settings.evening_enabled,
                morning_enabled=settings.morning_enabled,
            ),
        )

    @router.callback_query(F.data.startswith("tr_tog:"))
    async def handle_tr_toggle(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        kind = callback.data.split(":", 1)[1]
        if kind == "evening":
            await mediator.send(
                ToggleTrainingReminderCommand(telegram_user_id=callback.from_user.id, kind="evening"),
            )
        elif kind == "morning":
            await mediator.send(
                ToggleTrainingReminderCommand(telegram_user_id=callback.from_user.id, kind="morning"),
            )
        else:
            await callback.answer()
            return
        await _show_settings(callback)

    @router.callback_query(F.data.startswith("tr_yes:"))
    async def handle_tr_yes(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        if not isinstance(callback.message, Message):
            await callback.answer()
            return
        try:
            target = date.fromisoformat(callback.data.split(":", 1)[1])
        except ValueError:
            await callback.answer("Не понял дату")
            return
        await callback.answer()
        try:
            async with message_draft_scope(callback.bot, callback.message.chat.id):
                result = await mediator.send(
                    GenerateNextSessionCommand(
                        telegram_user_id=callback.from_user.id,
                        target_weekday=target.isoweekday(),
                    ),
                )
        except DomainError:
            await callback.message.answer(_KEEP_PLAN)
            return
        if result.agent_unavailable or result.schema_failed or result.document is None:
            await callback.message.answer(_KEEP_PLAN)
            return
        intro = "Ок. Вот черновик — программа не меняется, пока не подтвердишь."
        reply = f"{intro}\n\n{result.reply}".strip() if result.reply else intro
        await render_next_session_proposal(
            jinja_env=jinja_env,
            message=callback.message,
            reply=reply,
            document=result.document,
            telegram_user_id=callback.from_user.id,
        )

    @router.callback_query(F.data.startswith("tr_skip:"))
    async def handle_tr_skip(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        try:
            target = date.fromisoformat(callback.data.split(":", 1)[1])
        except ValueError:
            await callback.answer("Не понял дату")
            return
        result = await mediator.send(
            SkipTrainingDayCommand(telegram_user_id=callback.from_user.id, local_date=target),
        )
        await _answer(callback, _skip_text(result), reply_markup=back_to_menu_keyboard())

    return router


def _weekday(weekday: int) -> str:
    return WEEKDAY_LABELS.get(weekday, str(weekday))


def _skip_text(result) -> str:
    if result.outcome == "shifted":
        lines = [
            f"«{move.title}»: {_weekday(move.from_weekday)} → {_weekday(move.to_weekday)}" for move in result.moves
        ]
        return "Ок, перенёс тренировку.\n" + "\n".join(lines)
    messages = {
        "rest": "Этот день и так выходной, план не менял.",
        "already_done": "Эта тренировка уже сделана, план не менял.",
        "in_progress": "Сначала закончи текущую тренировку — план не менял.",
        "no_program": "Активной программы нет, переносить нечего.",
        "cannot_shift": "В неделе нет выходного, куда сдвинуть тренировку. План не менял.",
        "past": "Этот день уже прошёл, план не менял.",
    }
    return messages.get(result.outcome, "План не менял.")
