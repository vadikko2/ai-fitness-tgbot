from __future__ import annotations

from html import escape
from urllib.parse import quote
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput, ProgramStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.program_catalog import program_status_label, program_type_label
from fitness_bot.domain.workout.document import WorkoutDocument
from fitness_bot.presentation.keyboards import (
    exercise_guide_keyboard,
    home_keyboard,
    library_card_keyboard,
    library_day_keyboard,
    library_delete_confirm_keyboard,
    library_edit_proposal_keyboard,
    library_home_keyboard,
    library_slot_keyboard,
    library_title_keyboard,
)
from fitness_bot.presentation.message_draft import assistant_parse_failure_text, message_draft_scope
from fitness_bot.presentation.routers.program import (
    _can_approve_program,
    _day_buttons,
    _day_view,
    _document_view,
    _load_exercise_names,
    _slot_button_items,
    _slot_view,
    render_proposal,
)
from fitness_bot.service.models.commands.catalog import (
    ApplyCatalogProgramCommand,
    ClaimProgramByCodeCommand,
    DeleteLibraryProgramCommand,
    ProposeLibraryProgramEditCommand,
    PublishProgramCommand,
    RenameLibraryProgramCommand,
    SaveProgramDraftCommand,
    UnpublishProgramCommand,
)
from fitness_bot.service.models.commands.program import ApproveProposalCommand, DiscardProposalCommand
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.coach import GetCatalogProgramQuery, ListProgramCatalogQuery
from fitness_bot.service.models.queries.match_exercises import GetExerciseGuideQuery

_bot_username_cache: str | None = None

LIBRARY_TITLE_FIELD_PREFIX = "library_title:"
LIBRARY_EDIT_FIELD_PREFIX = "library_edit:"
# Telegram caps a message at 4096 chars; switch the card to a per-day summary before that.
_CARD_TEXT_LIMIT = 3800
_STATUS_ICONS = {ProgramStatus.DRAFT.value: "📗", ProgramStatus.PUBLISHED.value: "📘"}


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
            code,
        ],
    )
    return "\n".join(lines)


def _program_share_url(*, title: str, code: str, bot_username: str | None) -> str:
    share_text = _program_share_text(title=title, code=code, bot_username=bot_username)
    preview = f"https://t.me/{bot_username.lstrip('@')}" if bot_username else "https://t.me"
    return f"https://t.me/share/url?url={quote(preview, safe='')}&text={quote(share_text, safe='')}"


def library_field_program_id(field: str | None, prefix: str) -> UUID | None:
    if not field or not field.startswith(prefix):
        return None
    try:
        return UUID(field.removeprefix(prefix))
    except ValueError:
        return None


def _library_list_label(item: object) -> str:
    status = str(getattr(item, "status", ""))
    label = f"{_STATUS_ICONS.get(status, '📗')} {getattr(item, 'title', '')} · {program_status_label(status)}"
    author = getattr(item, "author_label", None)
    if author and getattr(item, "source_program_id", None) is not None:
        label += f" · от {author}"
    return label


def _find_day(document: WorkoutDocument, day_position: int):
    return next((day for day in document.days if day.position == day_position), None)


async def _load_card(mediator: RequestMediator, *, telegram_user_id: int, program_id: UUID):
    result = await mediator.send(GetCatalogProgramQuery(telegram_user_id=telegram_user_id, program_id=program_id))
    if result.status not in {ProgramStatus.DRAFT.value, ProgramStatus.PUBLISHED.value}:
        raise DomainError("карточка удалена из библиотеки")
    return result


async def show_library_card(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    bot: Bot | None,
    telegram_user_id: int,
    program_id: UUID,
    status_line: str | None = None,
) -> None:
    try:
        result = await _load_card(mediator, telegram_user_id=telegram_user_id, program_id=program_id)
    except DomainError as exc:
        await message.answer(f"Не удалось открыть карточку: {exc}")
        return
    bot_username = await _resolve_bot_username(bot) if bot else None
    names = await _load_exercise_names(mediator)
    context = {
        "title": result.title,
        "status_icon": _STATUS_ICONS.get(result.status, "📗"),
        "status_label": program_status_label(result.status),
        "program_type_label": program_type_label(result.document.program_type),
        "author_label": result.author_label if result.source_program_id is not None else None,
        "code": result.distribution_code,
        "link": _program_deep_link(bot_username, result.distribution_code) if result.distribution_code else None,
        "claim_note": (
            "Это шаблон. Автор вас не видит, пока не подключитесь." if result.source_program_id is not None else ""
        ),
        "status_line": status_line,
        "document": _document_view(result.document, names),
    }
    template = jinja_env.get_template("library_card.j2")
    text = template.render(compact=False, **context)
    if len(text) > _CARD_TEXT_LIMIT:
        text = template.render(compact=True, **context)
    share_url = None
    if result.status == ProgramStatus.PUBLISHED.value and result.distribution_code:
        share_url = _program_share_url(title=result.title, code=result.distribution_code, bot_username=bot_username)
    await message.answer(
        text,
        reply_markup=library_card_keyboard(
            program_id=str(program_id),
            status=result.status,
            is_author_template=result.is_author_template,
            days=_day_buttons(result.document),
            share_url=share_url,
        ),
    )


async def save_document_to_library(
    *,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    document: WorkoutDocument,
    intro: str,
    has_draft: bool = False,
) -> None:
    """Save with an auto title, then let the user type a better one (or keep it)."""
    try:
        saved = await mediator.send(SaveProgramDraftCommand(telegram_user_id=telegram_user_id, document=document))
    except DomainError as exc:
        await message.answer(str(exc))
        return
    await mediator.send(
        ExpectInputCommand(
            telegram_user_id=telegram_user_id,
            expected_input=ExpectedInput.PROFILE_FIELD,
            expected_field=f"{LIBRARY_TITLE_FIELD_PREFIX}{saved.program_id}",
        ),
    )
    await message.answer(
        f"{intro}\n\n📚 Название: «{escape(saved.title)}».\n"
        "Чтобы назвать по-своему, просто напиши название (до 60 символов) или оставь это.\n\n"
        "Поделиться: карточка → «Опубликовать» → код/ссылка. Клиенту — Кабинет → Назначить.",
        reply_markup=library_title_keyboard(program_id=str(saved.program_id), has_draft=has_draft),
    )


async def apply_library_title(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    program_id: UUID,
    text: str,
) -> None:
    result = await mediator.send(
        RenameLibraryProgramCommand(telegram_user_id=telegram_user_id, program_id=program_id, title=text),
    )
    await show_library_card(
        jinja_env=jinja_env,
        mediator=mediator,
        message=message,
        bot=message.bot,
        telegram_user_id=telegram_user_id,
        program_id=result.program_id,
        status_line=f"🏷 Название сохранено: «{escape(result.title)}».",
    )


async def render_library_edit_proposal(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    program_id: UUID,
    document: WorkoutDocument,
    reply: str = "",
    telegram_user_id: int | None = None,
) -> None:
    await render_proposal(
        jinja_env=jinja_env,
        mediator=mediator,
        message=message,
        reply=reply,
        document=document,
        telegram_user_id=telegram_user_id,
        reply_markup=library_edit_proposal_keyboard(
            program_id=str(program_id),
            can_approve=_can_approve_program(document),
        ),
    )


async def handle_library_edit_utterance(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    program_id: UUID,
    text: str,
) -> None:
    assert message.from_user is not None
    draft_preview = ""
    try:
        async with message_draft_scope(message.bot, message.chat.id) as draft:
            result = await mediator.send(
                ProposeLibraryProgramEditCommand(
                    telegram_user_id=message.from_user.id,
                    program_id=program_id,
                    utterance=text,
                ),
            )
            draft_preview = draft.preview_text
    except DomainError as exc:
        await message.answer(f"Не получилось изменить карточку: {exc}")
        return
    if result.agent_unavailable:
        await message.answer(jinja_env.get_template("agent_unavailable.j2").render(), reply_markup=home_keyboard())
        return
    if result.schema_failed or result.document is None:
        await message.answer(
            assistant_parse_failure_text(result.reply or draft_preview),
            reply_markup=library_edit_proposal_keyboard(program_id=str(program_id), can_approve=False),
        )
        return
    await render_library_edit_proposal(
        jinja_env=jinja_env,
        mediator=mediator,
        message=message,
        program_id=program_id,
        document=result.document,
        reply=result.reply,
        telegram_user_id=message.from_user.id,
    )


def create_library_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="library")

    async def _card(callback: CallbackQuery, program_id: UUID, *, status_line: str | None = None) -> None:
        if isinstance(callback.message, Message):
            await show_library_card(
                jinja_env=jinja_env,
                mediator=mediator,
                message=callback.message,
                bot=callback.bot,
                telegram_user_id=callback.from_user.id,
                program_id=program_id,
                status_line=status_line,
            )

    @router.callback_query(F.data == "library")
    async def library_home(callback: CallbackQuery) -> None:
        result = await mediator.send(ListProgramCatalogQuery(telegram_user_id=callback.from_user.id))
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
                "📚 Библиотека программ\n"
                "Открой карточку: состав по дням, правка, переименование, публикация, применение себе."
            )
        items = [(str(item.program_id), _library_list_label(item)) for item in result.items]
        if callback.message:
            await callback.message.answer(text, reply_markup=library_home_keyboard(items))
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_card:"))
    async def card(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        await _card(callback, program_id)
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_day:"))
    async def card_day(callback: CallbackQuery) -> None:
        _, program_id_raw, day_raw = callback.data.split(":", 2)
        program_id = UUID(program_id_raw)
        day_position = int(day_raw)
        try:
            result = await _load_card(mediator, telegram_user_id=callback.from_user.id, program_id=program_id)
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        day = _find_day(result.document, day_position)
        if day is None or callback.message is None:
            if callback.message:
                await callback.message.answer("День не найден.")
            await callback.answer()
            return
        names = await _load_exercise_names(mediator)
        text = jinja_env.get_template("workout_day.j2").render(day=_day_view(day, names))
        await callback.message.answer(
            text,
            reply_markup=library_day_keyboard(
                program_id=str(program_id),
                day_position=day_position,
                slots=_slot_button_items(day, names),
            ),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_slot:"))
    async def card_slot(callback: CallbackQuery) -> None:
        _, program_id_raw, day_raw, slot_raw = callback.data.split(":", 3)
        program_id = UUID(program_id_raw)
        day_position, slot_position = int(day_raw), int(slot_raw)
        try:
            result = await _load_card(mediator, telegram_user_id=callback.from_user.id, program_id=program_id)
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        day = _find_day(result.document, day_position)
        slot = None if day is None else next((item for item in day.slots if item.position == slot_position), None)
        if slot is None or callback.message is None:
            if callback.message:
                await callback.message.answer("Упражнение не найдено.")
            await callback.answer()
            return
        names = await _load_exercise_names(mediator)
        text = jinja_env.get_template("program_slot.j2").render(slot=_slot_view(slot, names))
        await callback.message.answer(
            text,
            reply_markup=library_slot_keyboard(
                program_id=str(program_id),
                day_position=day_position,
                slot_position=slot_position,
                has_catalog_guide=slot.exercise_id is not None,
            ),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_how:"))
    async def card_how(callback: CallbackQuery) -> None:
        _, program_id_raw, day_raw, slot_raw = callback.data.split(":", 3)
        program_id = UUID(program_id_raw)
        day_position, slot_position = int(day_raw), int(slot_raw)
        try:
            result = await _load_card(mediator, telegram_user_id=callback.from_user.id, program_id=program_id)
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        day = _find_day(result.document, day_position)
        slot = None if day is None else next((item for item in day.slots if item.position == slot_position), None)
        if slot is None or slot.exercise_id is None or callback.message is None:
            if callback.message:
                await callback.message.answer("Для этого упражнения нет техники из каталога.")
            await callback.answer()
            return
        guide = await mediator.send(GetExerciseGuideQuery(exercise_id=slot.exercise_id))
        if not guide.found:
            await callback.message.answer("Не нашёл технику для этого упражнения.")
            await callback.answer()
            return
        text = jinja_env.get_template("exercise_guide.j2").render(
            name=guide.name,
            technique=guide.technique,
            videos=[{"platform": item.platform, "url": item.url, "title": item.title} for item in guide.videos],
        )
        await callback.message.answer(
            text,
            reply_markup=exercise_guide_keyboard(
                videos=[(item.platform, item.url, item.title) for item in guide.videos],
                back_callback=f"lib_slot:{program_id}:{day_position}:{slot_position}",
            ),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_rename:"))
    async def rename(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.PROFILE_FIELD,
                expected_field=f"{LIBRARY_TITLE_FIELD_PREFIX}{program_id}",
            ),
        )
        if callback.message:
            await callback.message.answer(
                "🏷 Напиши новое название программы (до 60 символов).",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"lib_title_keep:{program_id}")],
                    ],
                ),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_title_keep:"))
    async def title_keep(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        await mediator.send(
            ExpectInputCommand(telegram_user_id=callback.from_user.id, expected_input=ExpectedInput.NONE),
        )
        await _card(callback, program_id)
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_edit:"))
    async def edit(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        try:
            result = await _load_card(mediator, telegram_user_id=callback.from_user.id, program_id=program_id)
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.PROPOSAL_UTTERANCE,
                expected_field=f"{LIBRARY_EDIT_FIELD_PREFIX}{program_id}",
            ),
        )
        note = ""
        if result.status == ProgramStatus.PUBLISHED.value:
            note = (
                "\nПрограмма опубликована: новые получатели по коду увидят обновлённую версию, "
                "у уже забравших — их копии."
            )
        if callback.message:
            await callback.message.answer(
                f"✏️ Что поменять в «{escape(result.title)}»? Напиши или продиктуй голосом.\n"
                f"Активный план это не затронет.{note}",
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_edit_ok:"))
    async def edit_ok(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        result = await mediator.send(ApproveProposalCommand(telegram_user_id=callback.from_user.id))
        if not isinstance(callback.message, Message):
            await callback.answer()
            return
        if result.blocked_empty or result.blocked_schedule or result.blocked_unresolved:
            template = (
                "proposal_unresolved_blocked.j2"
                if result.blocked_unresolved
                else "proposal_schedule_blocked.j2"
                if result.blocked_schedule
                else "proposal_empty_blocked.j2"
            )
            text = jinja_env.get_template(template).render()
            if result.document is not None:
                await render_library_edit_proposal(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=callback.message,
                    program_id=program_id,
                    document=result.document,
                    reply=text,
                    telegram_user_id=callback.from_user.id,
                )
            else:
                await callback.message.answer(text)
            await callback.answer()
            return
        if result.library_program_id is None:
            await callback.message.answer("Черновик подтверждён.", reply_markup=home_keyboard())
            await callback.answer()
            return
        await _card(callback, result.library_program_id, status_line="💾 Изменения сохранены в карточку.")
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_edit_cancel:"))
    async def edit_cancel(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        try:
            await mediator.send(DiscardProposalCommand(telegram_user_id=callback.from_user.id))
        except DomainError:
            pass
        await _card(callback, program_id, status_line="Правка отменена.")
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_del:"))
    async def delete(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        try:
            result = await _load_card(mediator, telegram_user_id=callback.from_user.id, program_id=program_id)
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        note = ""
        if result.status == ProgramStatus.PUBLISHED.value:
            note = "\nПубликация снимется, код перестанет работать. Копии у тех, кто уже забрал, останутся."
        if callback.message:
            await callback.message.answer(
                f"🗑 Удалить «{escape(result.title)}» из библиотеки?{note}",
                reply_markup=library_delete_confirm_keyboard(program_id=str(program_id)),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("lib_del_ok:"))
    async def delete_ok(callback: CallbackQuery) -> None:
        program_id = UUID(callback.data.split(":", 1)[1])
        try:
            result = await mediator.send(
                DeleteLibraryProgramCommand(telegram_user_id=callback.from_user.id, program_id=program_id),
            )
            text = f"Карточка «{escape(result.title)}» удалена из библиотеки."
        except DomainError as exc:
            text = f"Не удалось удалить: {exc}"
        if callback.message:
            await callback.message.answer(
                text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="📚 Библиотека", callback_data="library")]],
                ),
            )
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
            text = f"Опубликовано «{escape(result.title)}».\nКод: <code>{result.distribution_code}</code>\n"
            if link:
                text += f"Ссылка: {link}\n"
            else:
                text += f"Ссылка: start=p_{result.distribution_code}\n"
            text += (
                "Друг вставляет код в Библиотеке или открывает ссылку.\nСвоему клиенту: Кабинет → клиент → Назначить."
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
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(str(exc))
            await callback.answer()
            return
        await _card(callback, program_id, status_line="Публикация снята. Копии у людей остаются.")
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
