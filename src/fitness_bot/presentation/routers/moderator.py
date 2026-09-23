from __future__ import annotations

from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.domain.errors import DomainError
from fitness_bot.service.models.commands.coach import (
    ApproveCoachApplicationCommand,
    GrantModeratorCommand,
    RejectCoachApplicationCommand,
    ResolveCoachReportCommand,
    RevokeModeratorCommand,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.coach import ListModeratorsQuery, ListPendingCoachApplicationsQuery


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def apply_moderator_resolution_edits(*, bot: Bot | None, result) -> None:
    """Edit all stored moderator copies to the resolved status text (fan-out)."""
    if bot is None:
        return
    status_text = getattr(result, "status_text", None) or "Заявка обработана."
    for ref in getattr(result, "moderator_message_refs", None) or []:
        chat_id = ref.get("chat_id")
        message_id = ref.get("message_id")
        if chat_id is None or message_id is None:
            continue
        try:
            await bot.edit_message_text(status_text, chat_id=chat_id, message_id=message_id)
        except Exception:
            try:
                await bot.edit_message_caption(status_text, chat_id=chat_id, message_id=message_id)
            except Exception:
                pass
    applicant_chat_id = getattr(result, "applicant_chat_id", None)
    if applicant_chat_id and not getattr(result, "already_processed", False):
        try:
            await bot.send_message(applicant_chat_id, status_text)
        except Exception:
            pass


def create_moderator_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="moderator")

    async def _show_queue(target: Message | CallbackQuery, telegram_user_id: int) -> None:
        try:
            result = await mediator.send(ListPendingCoachApplicationsQuery(telegram_user_id=telegram_user_id))
        except DomainError as exc:
            text = str(exc)
            if isinstance(target, CallbackQuery) and target.message:
                await target.message.answer(text)
            elif isinstance(target, Message):
                await target.answer(text)
            return
        if not result.items:
            text = "Очередь заявок пуста."
            kb = _kb(
                [
                    [InlineKeyboardButton(text="Модераторы", callback_data="mod_list")],
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
                ],
            )
        else:
            text = "Заявки на статус тренера:"
            rows = []
            for item in result.items:
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=item.display_name,
                            callback_data=f"mod_app:{item.application_id}",
                        ),
                    ],
                )
            rows.append([InlineKeyboardButton(text="Модераторы", callback_data="mod_list")])
            rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="home")])
            kb = _kb(rows)
        if isinstance(target, CallbackQuery) and target.message:
            await target.message.answer(text, reply_markup=kb)
        elif isinstance(target, Message):
            await target.answer(text, reply_markup=kb)

    @router.message(Command("mod"))
    async def mod_cmd(message: Message) -> None:
        await _show_queue(message, message.from_user.id)

    @router.callback_query(F.data == "mod")
    async def mod_menu(callback: CallbackQuery) -> None:
        await _show_queue(callback, callback.from_user.id)
        await callback.answer()

    @router.callback_query(F.data.startswith("mod_app:"))
    async def app_card(callback: CallbackQuery) -> None:
        app_id = callback.data.split(":", 1)[1]
        try:
            result = await mediator.send(ListPendingCoachApplicationsQuery(telegram_user_id=callback.from_user.id))
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        item = next((x for x in result.items if str(x.application_id) == app_id), None)
        if item is None:
            text = "Заявка уже обработана или не найдена."
            kb = _kb([[InlineKeyboardButton(text="Очередь", callback_data="mod")]])
        else:
            text = f"{item.display_name}\n{item.bio}\nПортфолио: {item.portfolio_url}"
            kb = _kb(
                [
                    [
                        InlineKeyboardButton(text="✅ Approve", callback_data=f"mod_c_ok:{item.application_id}"),
                        InlineKeyboardButton(text="❌ Reject", callback_data=f"mod_c_no:{item.application_id}"),
                    ],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="mod")],
                ],
            )
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("mod_c_ok:"))
    async def approve(callback: CallbackQuery) -> None:
        app_id = UUID(callback.data.split(":", 1)[1])
        try:
            result = await mediator.send(
                ApproveCoachApplicationCommand(telegram_user_id=callback.from_user.id, application_id=app_id),
            )
            text = "Заявка уже обработана." if result.already_processed else "Заявка одобрена."
            await apply_moderator_resolution_edits(bot=callback.bot, result=result)
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    @router.callback_query(F.data.startswith("mod_c_no:"))
    async def reject_start(callback: CallbackQuery) -> None:
        app_id = callback.data.split(":", 1)[1]
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.MODERATOR_REJECT_COMMENT,
                expected_field=app_id,
            ),
        )
        if callback.message:
            await callback.message.answer("Почему отказ? Напишите комментарий.")
        await callback.answer()

    @router.callback_query(F.data == "mod_list")
    async def list_mods(callback: CallbackQuery) -> None:
        try:
            result = await mediator.send(ListModeratorsQuery(telegram_user_id=callback.from_user.id))
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        lines = []
        for item in result.items:
            label = item.display_name or item.telegram_username or str(item.telegram_user_id)
            lines.append(f"• {label} ({item.telegram_user_id})")
        text = "Модераторы:\n" + ("\n".join(lines) if lines else "пусто")
        kb = _kb(
            [
                [InlineKeyboardButton(text="Добавить (telegram id)", callback_data="mod_grant")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="mod")],
            ],
        )
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data == "mod_grant")
    async def grant_prompt(callback: CallbackQuery) -> None:
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.PROFILE_FIELD,
                expected_field="moderator_grant_telegram_id",
            ),
        )
        if callback.message:
            await callback.message.answer("Пришлите numeric telegram id нового модератора.")
        await callback.answer()

    @router.callback_query(F.data.startswith("mod_rep_ok:"))
    async def resolve_report(callback: CallbackQuery) -> None:
        report_id = UUID(callback.data.split(":", 1)[1])
        try:
            await mediator.send(
                ResolveCoachReportCommand(
                    telegram_user_id=callback.from_user.id,
                    report_id=report_id,
                    suspend=False,
                ),
            )
            text = "Жалоба закрыта."
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    @router.callback_query(F.data.startswith("mod_rep_suspend:"))
    async def suspend_from_report(callback: CallbackQuery) -> None:
        report_id = UUID(callback.data.split(":", 1)[1])
        try:
            await mediator.send(
                ResolveCoachReportCommand(
                    telegram_user_id=callback.from_user.id,
                    report_id=report_id,
                    suspend=True,
                ),
            )
            text = "Тренер приостановлен, жалоба закрыта."
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    # silence unused imports used by text router for grant/revoke
    _ = (GrantModeratorCommand, RevokeModeratorCommand, RejectCoachApplicationCommand, jinja_env)
    return router
