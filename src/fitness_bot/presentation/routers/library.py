from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.errors import DomainError
from fitness_bot.service.models.commands.catalog import (
    ApplyCatalogProgramCommand,
    ClaimProgramByCodeCommand,
    PublishProgramCommand,
    UnpublishProgramCommand,
)
from fitness_bot.service.models.queries.coach import GetCatalogProgramQuery, ListProgramCatalogQuery


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_library_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="library")

    @router.callback_query(F.data == "library")
    async def library_home(callback: CallbackQuery) -> None:
        result = await mediator.send(ListProgramCatalogQuery(telegram_user_id=callback.from_user.id))
        rows = [
            [InlineKeyboardButton(text="🔗 Ввести код или ссылку", callback_data="code_link")],
            [InlineKeyboardButton(text="➕ Создать через AI", callback_data="prog_setup")],
        ]
        if not result.items:
            text = "Библиотека программ пуста."
        else:
            text = "Библиотека программ:"
            for item in result.items:
                badge = f" · {item.status}"
                if item.author_label:
                    badge += f" · от {item.author_label}"
                rows.insert(
                    -2,
                    [
                        InlineKeyboardButton(
                            text=f"{item.title}{badge}",
                            callback_data=f"lib_card:{item.program_id}",
                        ),
                    ],
                )
        rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="home")])
        if callback.message:
            await callback.message.answer(text, reply_markup=_kb(rows))
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_card:"))
    async def card(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        try:
            result = await mediator.send(
                GetCatalogProgramQuery(telegram_user_id=callback.from_user.id, program_id=program_id),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        claim_note = ""
        if result.source_program_id is not None:
            claim_note = "\nЭто шаблон. Автор вас не видит, пока не подключитесь."
        code_line = ""
        if result.distribution_code:
            code_line = f"\nКод: {result.distribution_code}\nСсылка: start=p_{result.distribution_code}"
        text = f"{result.title}\nСтатус: {result.status}{code_line}{claim_note}"
        rows = [
            [InlineKeyboardButton(text="Применить сейчас", callback_data=f"lib_apply:{program_id}:adapt")],
            [InlineKeyboardButton(text="Как у автора", callback_data=f"lib_apply:{program_id}:as_is")],
        ]
        if result.status == "draft" and result.is_author_template:
            rows.append([InlineKeyboardButton(text="Опубликовать", callback_data=f"lib_pub:{program_id}")])
        if result.status == "published":
            rows.append([InlineKeyboardButton(text="Снять с публикации", callback_data=f"lib_unpub:{program_id}")])
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="library")])
        if callback.message:
            await callback.message.answer(text, reply_markup=_kb(rows))
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_pub:"))
    async def publish(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        try:
            result = await mediator.send(
                PublishProgramCommand(telegram_user_id=callback.from_user.id, program_id=program_id),
            )
            text = (
                f"Опубликовано «{result.title}».\n"
                f"Код: {result.distribution_code}\n"
                f"Ссылка для всех: start=p_{result.distribution_code}\n"
                "Своему клиенту: Кабинет → клиент → Назначить."
            )
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_unpub:"))
    async def unpublish(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        try:
            await mediator.send(
                UnpublishProgramCommand(telegram_user_id=callback.from_user.id, program_id=program_id),
            )
            text = "Публикация снята. Копии у людей остаются."
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_apply:"))
    async def apply(callback: CallbackQuery) -> None:
        _, program_id_raw, mode = callback.data.split(":", 2)
        program_id = UUID(program_id_raw)
        try:
            result = await mediator.send(
                ApplyCatalogProgramCommand(
                    telegram_user_id=callback.from_user.id,
                    program_id=program_id,
                    mode=mode,
                ),
            )
            if result.mode == "as_is" and result.active_program_id:
                text = "План активирован как «Мой план сейчас»."
            else:
                diff = result.adapt_diff or result.reply or ""
                text = f"Подстроили план.\n{diff}\nПодтвердите proposal как обычно."
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    # ClaimProgramByCode used from text router
    _ = (ClaimProgramByCodeCommand, jinja_env)
    return router
