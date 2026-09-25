from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.program_catalog import program_status_label
from fitness_bot.presentation.keyboards import how_it_works_button
from fitness_bot.service.models.commands.catalog import (
    ApplyCatalogProgramCommand,
    ClaimProgramByCodeCommand,
    PublishProgramCommand,
    UnpublishProgramCommand,
)
from fitness_bot.service.models.queries.coach import GetCatalogProgramQuery, ListProgramCatalogQuery

_bot_username_cache: str | None = None


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _resolve_bot_username(bot: Bot) -> str | None:
    global _bot_username_cache
    if _bot_username_cache:
        return _bot_username_cache
    try:
        me = await bot.get_me()
    except Exception:
        return None
    if me.username:
        _bot_username_cache = me.username
        return _bot_username_cache
    return None


def _program_deep_link(bot_username: str | None, code: str) -> str | None:
    if not bot_username:
        return None
    return f"https://t.me/{bot_username.lstrip('@')}?start=p_{code}"


def _program_share_text(*, title: str, code: str, bot_username: str | None) -> str:
    link = _program_deep_link(bot_username, code)
    lines = [
        f"Программа «{title}» в AI Fitness.",
        "",
    ]
    if link:
        lines.extend([f"Открой в боте:\n{link}", ""])
    lines.extend(
        [
            "Или Библиотека → «Ввести код или ссылку»:",
            f"`{code}`",
        ],
    )
    return "\n".join(lines)


def _program_share_url(*, title: str, code: str, bot_username: str | None) -> str:
    share_text = _program_share_text(title=title, code=code, bot_username=bot_username)
    preview = f"https://t.me/{bot_username.lstrip('@')}" if bot_username else "https://t.me"
    return f"https://t.me/share/url?url={quote(preview, safe='')}&text={quote(share_text, safe='')}"


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
            text = (
                "Библиотека программ пуста.\n\n"
                "Сюда попадают шаблоны: после генерации нажми «Сохранить в библиотеку», "
                "либо введи чужой код/ссылку.\n"
                "Поделиться своей: сохрани → открой карточку → «Опубликовать» "
                "→ отправь код."
            )
        else:
            text = (
                "Библиотека программ:\n" "Карточка → применить себе, опубликовать (код/ссылка) или назначить клиенту."
            )
            for item in result.items:
                badge = f" · {program_status_label(item.status)}"
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
        rows.append([how_it_works_button("library")])
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
        bot_username = await _resolve_bot_username(callback.bot) if callback.bot else None
        claim_note = ""
        if result.source_program_id is not None:
            claim_note = "\nЭто шаблон. Автор вас не видит, пока не подключитесь."
        code_line = ""
        if result.distribution_code:
            link = _program_deep_link(bot_username, result.distribution_code)
            code_line = f"\nКод: `{result.distribution_code}`"
            if link:
                code_line += f"\nСсылка: {link}"
            else:
                code_line += f"\nСсылка: start=p_{result.distribution_code}"
        text = f"{result.title}\nСтатус: {program_status_label(result.status)}{code_line}{claim_note}"
        rows = [
            [InlineKeyboardButton(text="Применить сейчас", callback_data=f"lib_apply:{program_id}:adapt")],
            [InlineKeyboardButton(text="Как у автора", callback_data=f"lib_apply:{program_id}:as_is")],
        ]
        if result.status == "draft" and result.is_author_template:
            rows.append(
                [InlineKeyboardButton(text="Опубликовать и получить код", callback_data=f"lib_pub:{program_id}")],
            )
        if result.status == "published" and result.distribution_code:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="📤 Отправить код другу",
                        url=_program_share_url(
                            title=result.title,
                            code=result.distribution_code,
                            bot_username=bot_username,
                        ),
                    ),
                ],
            )
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
            bot_username = await _resolve_bot_username(callback.bot) if callback.bot else None
            link = _program_deep_link(bot_username, result.distribution_code)
            text = f"Опубликовано «{result.title}».\n" f"Код: `{result.distribution_code}`\n"
            if link:
                text += f"Ссылка: {link}\n"
            else:
                text += f"Ссылка: start=p_{result.distribution_code}\n"
            text += (
                "Друг вставляет код в Библиотеке или открывает ссылку.\n"
                "Своему клиенту: Кабинет → клиент → Назначить."
            )
            rows = [
                [
                    InlineKeyboardButton(
                        text="📤 Отправить код другу",
                        url=_program_share_url(
                            title=result.title,
                            code=result.distribution_code,
                            bot_username=bot_username,
                        ),
                    ),
                ],
                [InlineKeyboardButton(text="Открыть карточку", callback_data=f"lib_card:{program_id}")],
                [InlineKeyboardButton(text="📚 Библиотека", callback_data="library")],
            ]
            kb = _kb(rows)
        except DomainError as exc:
            text = str(exc)
            kb = _kb(
                [
                    [InlineKeyboardButton(text="📚 Библиотека", callback_data="library")],
                ],
            )
        if callback.message:
            await callback.message.answer(text, reply_markup=kb)
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
                text = f"Подстроили план.\n{diff}\nПодтвердите черновик как обычно."
        except DomainError as exc:
            text = str(exc)
        if callback.message:
            await callback.message.answer(text)
        await callback.answer()

    # ClaimProgramByCode used from text router
    _ = (ClaimProgramByCodeCommand, jinja_env)
    return router
