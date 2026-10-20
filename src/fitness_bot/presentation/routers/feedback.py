from __future__ import annotations

from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message
from cqrs import RequestMediator

from fitness_bot.domain.enums import ExpectedInput, FeedbackKind, FeedbackStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.feedback.ticket import FEEDBACK_PAGE_SIZE
from fitness_bot.presentation.chat_pages import push_scope
from fitness_bot.presentation.keyboards import (
    feedback_author_notice_keyboard,
    feedback_compose_keyboard,
    feedback_detail_keyboard,
    feedback_list_keyboard,
    feedback_menu_keyboard,
    feedback_moderator_keyboard,
    feedback_status_mark,
)
from fitness_bot.service.models.commands.feedback import (
    ChangeFeedbackStatusCommand,
    RecordFeedbackModeratorMessageCommand,
    SubmitFeedbackCommand,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.feedback import GetMyFeedbackQuery, ListMyFeedbackQuery

_STATUS_LABEL = {
    FeedbackStatus.NEW: "ожидает",
    FeedbackStatus.IN_PROGRESS: "в работе",
    FeedbackStatus.RESOLVED: "решено",
    FeedbackStatus.CANCELLED: "отменено",
}

_COPY = {
    FeedbackKind.IDEA: {
        "menu": "Есть идея",
        "hint": (
            "Если есть мысль, как сделать общение удобнее — напиши её своими словами. "
            "Можно голосом, но лучше текстом. До 3 картинок можно прислать сразу или дослать, "
            "пока не нажмёшь «Отправить»."
        ),
        "ask": (
            "Напиши идею: что сейчас неудобно и как было бы лучше. "
            "Можно голосом, но лучше текстом. Картинки — до 3 штук — присылай в любой момент, "
            "пока не нажмёшь «Отправить»."
        ),
        "photos": "Текст у меня. Можно дослать до 3 картинок или нажать «Отправить».",
        "sent": "Идею передал. Её посмотрят и, если возьмут в работу, я напишу сюда.",
        "undelivered": "Идею я сохранил, но до человека она сейчас не дошла. Попробуй отправить ещё раз чуть позже.",
        "no_moderator": "Идею я сохранил. Сейчас некому её сразу показать — она не потеряется.",
        "empty": "Идей пока нет. Когда напишешь первую, она появится здесь.",
        "list": "Мои идеи",
        "mod": "💡 Новая идея",
        "taken": "Твою идею взяли в работу. Когда будет что сказать — напишу сюда.",
        "resolved_text": "Твою идею закрыли: отметили как решённую.",
        "cancelled": "Твою идею отменили. Ниже — почему.",
    },
    FeedbackKind.PROBLEM: {
        "menu": "Сообщить о проблеме",
        "hint": (
            "Если что-то сломалось или ведёт себя не так — расскажи, что ты нажимал и что увидел. "
            "Можно голосом, но лучше текстом. До 3 картинок можно прислать сразу или дослать, "
            "пока не нажмёшь «Отправить»."
        ),
        "ask": (
            "Опиши проблему: что хотел сделать и что произошло вместо этого. "
            "Можно голосом, но лучше текстом. Картинки — до 3 штук — присылай в любой момент, "
            "пока не нажмёшь «Отправить»."
        ),
        "photos": "Текст у меня. Пришли до 3 картинок, если есть что показать, или нажми «Отправить».",
        "sent": "Передал. Когда возьмут в работу или закроют, я напишу сюда.",
        "undelivered": "Сообщение я сохранил, но до человека оно сейчас не дошло. Отправь ещё раз чуть позже.",
        "no_moderator": "Сообщение я сохранил. Сейчас некому сразу его показать — оно не потеряется.",
        "empty": "Сообщений о проблемах пока нет.",
        "list": "Мои сообщения",
        "mod": "⚠️ Новая проблема",
        "taken": "Твоё сообщение о проблеме взяли в работу. Когда будет что сказать — напишу сюда.",
        "resolved_text": "Твоё сообщение о проблеме закрыли и отметили как решённым.",
        "cancelled": "Твоё сообщение о проблеме отменили. Ниже — почему.",
    },
}

_ERROR_TEXT = {
    "text is required": "Напиши хотя бы пару слов — пустое сообщение передать нечего.",
    "text must be ≤2000 characters": "Текст длиннее 2000 символов. Сократи, самое важное оставь в начале.",
    "at most 3 photos": "Картинок можно приложить не больше трёх. Выбери те, без которых непонятно.",
    "photo is required": "Здесь нужна картинка, текстом этот шаг не закрыть.",
    "feedback photo must be an image": "Это не картинка. Пришли фото, чтобы было видно, о чём речь.",
    "feedback photo size must be between 1 and 10 MiB": "Картинка тяжелее 10 МБ. Сожми её и пришли ещё раз.",
    "already sent": "Это сообщение уже ушло, второй раз отправлять не нужно.",
    "photos can be attached only before sending": "Картинку можно добавить, пока сообщение ещё не отправлено.",
    "already in this status": "Уже стоит этот статус, менять не на что.",
    "status cannot change": "Этот статус уже финальный, назад его не откатить.",
    "cancel reply is required": "Напиши автору, почему отменяешь — пустой отказ ему ничего не объяснит.",
    "reply must be ≤2000 characters": "Ответ длиннее 2000 символов. Сократи до сути.",
    "feedback not found": "Это сообщение уже не найти. Открой список ещё раз.",
    "moderator role required": "Это действие только для модератора.",
    "user not found": "Сначала открой бота через /start, чтобы я тебя узнал.",
}


def feedback_error_text(exc: Exception) -> str:
    return _ERROR_TEXT.get(str(exc), str(exc))


def author_status_text(*, kind: FeedbackKind, status: FeedbackStatus, reply: str | None) -> str:
    copy = _COPY[kind]
    if status == FeedbackStatus.IN_PROGRESS:
        return copy["taken"]
    if status == FeedbackStatus.RESOLVED:
        return copy["resolved_text"]
    answer = reply or ""
    return f"{copy['cancelled']}\n\nОтвет: {answer}"


def moderator_card_text(
    *,
    kind: FeedbackKind,
    body: str,
    author_name: str | None,
    status: FeedbackStatus | None = None,
    reply: str | None = None,
) -> str:
    copy = _COPY[kind]
    who = author_name or "без имени"
    lines = [copy["mod"], f"От: {who}", "", body]
    if status is not None and status != FeedbackStatus.NEW:
        lines.insert(1, f"Статус: {_STATUS_LABEL[status]}")
        if reply:
            lines.insert(2, f"Ответ: {reply}")
    return "\n".join(lines)


def detail_text(*, status: FeedbackStatus, body: str, reply: str | None, created_at) -> str:
    when = created_at.strftime("%d.%m.%Y")
    lines = [f"{feedback_status_mark(status)} {_STATUS_LABEL[status]}", when, "", body]
    if reply:
        lines.extend(["", f"Ответ: {reply}"])
    return "\n".join(lines)


_CAPTION_LIMIT = 1024


async def send_text_with_photos(
    bot: Bot,
    *,
    chat_id: int,
    text: str,
    file_ids: list[str],
    keyboard,
    album_followup: str,
):
    """Photo and text in one message. Several photos become one album, buttons sit on the next line."""
    photos = [file_id for file_id in file_ids if file_id]
    if not photos:
        return await bot.send_message(chat_id, text, reply_markup=keyboard)
    caption = text if len(text) <= _CAPTION_LIMIT else None
    if len(photos) == 1 and caption is not None:
        return await bot.send_photo(chat_id, photos[0], caption=caption, reply_markup=keyboard)
    if len(photos) == 1:
        await bot.send_photo(chat_id, photos[0], reply_markup=keyboard)
        return await bot.send_message(chat_id, text, reply_markup=keyboard)
    media = [InputMediaPhoto(media=photos[0], caption=caption)]
    media.extend(InputMediaPhoto(media=file_id) for file_id in photos[1:])
    await bot.send_media_group(chat_id, media)
    followup = album_followup if caption is not None else text
    return await bot.send_message(chat_id, followup, reply_markup=keyboard)


async def deliver_feedback_to_moderators(*, bot: Bot, mediator: RequestMediator, result) -> int:
    text = moderator_card_text(
        kind=result.kind,
        body=result.body,
        author_name=result.author_display_name,
        status=FeedbackStatus.NEW,
    )
    keyboard = feedback_moderator_keyboard(result.ticket_id)
    delivered = 0
    for chat in result.moderator_chats:
        chat_id = chat.get("chat_id")
        moderator_user_id = chat.get("user_id")
        if chat_id is None or moderator_user_id is None:
            continue
        try:
            sent = await send_text_with_photos(
                bot,
                chat_id=chat_id,
                text=text,
                file_ids=list(result.photo_file_ids),
                keyboard=keyboard,
                album_followup="Кнопки к сообщению выше.",
            )
        except Exception:
            continue
        try:
            await mediator.send(
                RecordFeedbackModeratorMessageCommand(
                    ticket_id=result.ticket_id,
                    moderator_user_id=UUID(str(moderator_user_id)),
                    chat_id=chat_id,
                    message_id=sent.message_id,
                ),
            )
        except Exception:
            pass
        delivered += 1
    return delivered


async def notify_feedback_status(*, bot: Bot | None, result) -> None:
    if bot is None:
        return
    card = moderator_card_text(
        kind=result.kind,
        body=result.body,
        author_name=result.author_display_name,
        status=result.status,
        reply=result.moderator_reply,
    )
    for ref in result.moderator_message_refs:
        chat_id = ref.get("chat_id")
        message_id = ref.get("message_id")
        if chat_id is None or message_id is None:
            continue
        try:
            await bot.edit_message_text(card, chat_id=chat_id, message_id=message_id, reply_markup=None)
        except Exception:
            try:
                await bot.edit_message_caption(card, chat_id=chat_id, message_id=message_id, reply_markup=None)
            except Exception:
                pass
    if result.author_chat_id is None:
        return
    notice = author_status_text(kind=result.kind, status=result.status, reply=result.moderator_reply)
    try:
        with push_scope(int(result.author_chat_id)):
            await bot.send_message(
                result.author_chat_id,
                notice,
                reply_markup=feedback_author_notice_keyboard(result.ticket_id),
            )
    except Exception:
        pass


def submit_ack(*, kind: FeedbackKind, moderator_count: int, delivered: int) -> str:
    copy = _COPY[kind]
    if moderator_count == 0:
        return copy["no_moderator"]
    if delivered == 0:
        return copy["undelivered"]
    return copy["sent"]


def create_feedback_router(*, mediator: RequestMediator) -> Router:
    router = Router(name="feedback")

    def _parse_kind(raw: str) -> FeedbackKind | None:
        try:
            return FeedbackKind(raw)
        except ValueError:
            return None

    async def _answer(callback: CallbackQuery, text: str, **kwargs) -> None:
        if callback.message:
            await callback.message.answer(text, **kwargs)
        await callback.answer()

    async def _show_menu(callback: CallbackQuery, kind: FeedbackKind) -> None:
        copy = _COPY[kind]
        await _answer(callback, f"{copy['menu']}\n\n{copy['hint']}", reply_markup=feedback_menu_keyboard(kind))

    async def _show_list(callback: CallbackQuery, kind: FeedbackKind, offset: int) -> None:
        try:
            result = await mediator.send(
                ListMyFeedbackQuery(
                    telegram_user_id=callback.from_user.id,
                    kind=kind,
                    offset=offset,
                    limit=FEEDBACK_PAGE_SIZE,
                ),
            )
        except DomainError as exc:
            await _answer(callback, feedback_error_text(exc))
            return
        if result.total and result.offset >= result.total:
            last = ((result.total - 1) // FEEDBACK_PAGE_SIZE) * FEEDBACK_PAGE_SIZE
            result = await mediator.send(
                ListMyFeedbackQuery(
                    telegram_user_id=callback.from_user.id,
                    kind=kind,
                    offset=last,
                    limit=FEEDBACK_PAGE_SIZE,
                ),
            )
        copy = _COPY[kind]
        if result.total == 0:
            await _answer(callback, copy["empty"], reply_markup=feedback_menu_keyboard(kind))
            return
        start = result.offset + 1
        end = result.offset + len(result.items)
        text = f"{copy['list']}\n{start}–{end} из {result.total}"
        keyboard = feedback_list_keyboard(
            kind=kind,
            items=[(item.ticket_id, item.status, item.body) for item in result.items],
            offset=result.offset,
            total=result.total,
        )
        await _answer(callback, text, reply_markup=keyboard)

    @router.callback_query(F.data.startswith("fb_menu:"))
    async def open_menu(callback: CallbackQuery) -> None:
        kind = _parse_kind(callback.data.split(":", 1)[1])
        if kind is None:
            await callback.answer()
            return
        await _show_menu(callback, kind)

    @router.callback_query(F.data.startswith("fb_new:"))
    async def start_compose(callback: CallbackQuery) -> None:
        from fitness_bot.service.models.commands.feedback import StartFeedbackDraftCommand

        kind = _parse_kind(callback.data.split(":", 1)[1])
        if kind is None:
            await callback.answer()
            return
        try:
            draft = await mediator.send(
                StartFeedbackDraftCommand(
                    telegram_user_id=callback.from_user.id,
                    kind=kind,
                    body="",
                ),
            )
        except DomainError as exc:
            await _answer(callback, feedback_error_text(exc))
            return
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.FEEDBACK_PHOTO,
                expected_field=_compose_field(kind, draft.ticket_id),
            ),
        )
        await _answer(
            callback,
            _COPY[kind]["ask"],
            reply_markup=feedback_compose_keyboard(draft.ticket_id),
        )

    @router.callback_query(F.data == "fb_abort")
    async def abort_compose(callback: CallbackQuery) -> None:
        from fitness_bot.service.models.queries.users import GetWorkflowQuery

        workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=callback.from_user.id))
        kind = _parse_kind_value(workflow.expected_field)
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        if kind is None:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🏠 В меню", callback_data="home")]],
            )
        else:
            markup = feedback_menu_keyboard(kind)
        await _answer(
            callback,
            "Черновик убрал. Если мысль вернётся — напиши заново, ничего не потеряется из уже отправленного.",
            reply_markup=markup,
        )

    @router.callback_query(F.data.startswith("fb_list:"))
    async def open_list(callback: CallbackQuery) -> None:
        _, kind_raw, offset_raw = (callback.data.split(":", 2) + ["0", "0"])[:3]
        kind = _parse_kind(kind_raw)
        if kind is None:
            await callback.answer()
            return
        try:
            offset = int(offset_raw)
        except ValueError:
            offset = 0
        await _show_list(callback, kind, offset)

    @router.callback_query(F.data.startswith("fb_open:"))
    async def open_ticket(callback: CallbackQuery) -> None:
        try:
            ticket_id = UUID(callback.data.split(":", 1)[1])
            result = await mediator.send(
                GetMyFeedbackQuery(telegram_user_id=callback.from_user.id, ticket_id=ticket_id),
            )
        except (DomainError, ValueError) as exc:
            await _answer(callback, feedback_error_text(exc))
            return
        text = detail_text(
            status=result.status,
            body=result.body,
            reply=result.moderator_reply,
            created_at=result.created_at,
        )
        if callback.message is not None and callback.bot is not None:
            try:
                await send_text_with_photos(
                    callback.bot,
                    chat_id=callback.message.chat.id,
                    text=text,
                    file_ids=list(result.photo_file_ids),
                    keyboard=feedback_detail_keyboard(result.kind),
                    album_followup="К списку или в меню — кнопками ниже.",
                )
            except Exception:
                await callback.message.answer(text, reply_markup=feedback_detail_keyboard(result.kind))
        await callback.answer()

    @router.callback_query(F.data.startswith("fb_send:"))
    async def send_ticket(callback: CallbackQuery) -> None:
        try:
            ticket_id = UUID(callback.data.split(":", 1)[1])
            result = await mediator.send(
                SubmitFeedbackCommand(telegram_user_id=callback.from_user.id, ticket_id=ticket_id),
            )
        except (DomainError, ValueError) as exc:
            await _answer(callback, feedback_error_text(exc))
            return
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        delivered = 0
        if callback.bot is not None:
            delivered = await deliver_feedback_to_moderators(bot=callback.bot, mediator=mediator, result=result)
        text = submit_ack(
            kind=result.kind,
            moderator_count=len(result.moderator_chats),
            delivered=delivered,
        )
        await _answer(callback, text, reply_markup=feedback_menu_keyboard(result.kind))

    async def _change(callback: CallbackQuery, status: FeedbackStatus) -> None:
        try:
            ticket_id = UUID(callback.data.split(":", 1)[1])
            result = await mediator.send(
                ChangeFeedbackStatusCommand(
                    telegram_user_id=callback.from_user.id,
                    ticket_id=ticket_id,
                    status=status,
                ),
            )
        except (DomainError, ValueError) as exc:
            await _answer(callback, feedback_error_text(exc))
            return
        await notify_feedback_status(bot=callback.bot, result=result)
        ack = "Взяли в работу." if status == FeedbackStatus.IN_PROGRESS else "Отметили как решённое."
        await _answer(callback, ack)

    @router.callback_query(F.data.startswith("fb_ok:"))
    async def resolve_ticket(callback: CallbackQuery) -> None:
        await _change(callback, FeedbackStatus.RESOLVED)

    @router.callback_query(F.data.startswith("fb_work:"))
    async def progress_ticket(callback: CallbackQuery) -> None:
        await _change(callback, FeedbackStatus.IN_PROGRESS)

    @router.callback_query(F.data.startswith("fb_no:"))
    async def cancel_prompt(callback: CallbackQuery) -> None:
        ticket_id = callback.data.split(":", 1)[1]
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.FEEDBACK_CANCEL_REPLY,
                expected_field=ticket_id,
            ),
        )
        await _answer(
            callback,
            "Напиши автору, почему отменяешь. Он увидит этот текст вместе с отменой.",
        )

    return router


async def accept_feedback_image(
    *,
    message: Message,
    mediator: RequestMediator,
    file_id: str,
    body: bytes,
    content_type: str,
    expected_input: ExpectedInput,
    expected_field: str | None,
) -> bool:
    """Save a picture on an idea or problem draft. False when this step is something else."""
    from fitness_bot.service.models.commands.feedback import AttachFeedbackPhotoCommand, StartFeedbackDraftCommand

    assert message.from_user is not None
    if expected_input == ExpectedInput.FEEDBACK_PHOTO:
        await remember_feedback_photo(
            message=message,
            mediator=mediator,
            file_id=file_id,
            body=body,
            content_type=content_type,
        )
        return True
    if expected_input != ExpectedInput.FEEDBACK_TEXT:
        return False

    kind = _parse_kind_value(expected_field)
    if kind is None:
        await message.answer("Не вижу черновик. Открой «Есть идея» или «Сообщить о проблеме» ещё раз.")
        return True

    caption = (message.caption or "").strip()
    try:
        draft = await mediator.send(
            StartFeedbackDraftCommand(
                telegram_user_id=message.from_user.id,
                kind=kind,
                body=caption,
            ),
        )
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=message.from_user.id,
                expected_input=ExpectedInput.FEEDBACK_PHOTO,
                expected_field=_compose_field(kind, draft.ticket_id),
            ),
        )
        attached = await mediator.send(
            AttachFeedbackPhotoCommand(
                telegram_user_id=message.from_user.id,
                ticket_id=draft.ticket_id,
                file_id=file_id,
                body=body,
                content_type=content_type,
            ),
        )
    except DomainError as exc:
        await message.answer(feedback_error_text(exc))
        return True
    if caption:
        await _answer_photo_progress(message, ticket_id=attached.ticket_id, photo_count=attached.photo_count)
    else:
        await message.answer(
            f"Картинку сохранил. {_COPY[kind]['ask']}",
            reply_markup=feedback_compose_keyboard(attached.ticket_id),
        )
    return True


def _answer_photo_progress_text(photo_count: int) -> str:
    if photo_count >= 3:
        return "Все 3 картинки на месте. Можно нажимать «Отправить»."
    return f"Картинка {photo_count} из 3. Можно приложить ещё или нажать «Отправить», если уже достаточно."


async def _answer_photo_progress(message: Message, *, ticket_id: UUID, photo_count: int) -> None:
    await message.answer(
        _answer_photo_progress_text(photo_count),
        reply_markup=feedback_compose_keyboard(ticket_id),
    )


async def remember_feedback_photo(
    *,
    message: Message,
    mediator: RequestMediator,
    file_id: str,
    body: bytes,
    content_type: str,
) -> None:
    from fitness_bot.service.models.commands.feedback import AttachFeedbackPhotoCommand
    from fitness_bot.service.models.queries.users import GetWorkflowQuery

    assert message.from_user is not None
    workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=message.from_user.id))
    if workflow.expected_input != ExpectedInput.FEEDBACK_PHOTO:
        return
    ticket_id = _parse_uuid(workflow.expected_field)
    if ticket_id is None:
        await message.answer("Не вижу черновик. Открой «Есть идея» или «Сообщить о проблеме» ещё раз.")
        return
    try:
        result = await mediator.send(
            AttachFeedbackPhotoCommand(
                telegram_user_id=message.from_user.id,
                ticket_id=ticket_id,
                file_id=file_id,
                body=body,
                content_type=content_type,
            ),
        )
    except (DomainError, ValueError) as exc:
        markup = feedback_compose_keyboard(ticket_id) if ticket_id is not None else None
        await message.answer(feedback_error_text(exc), reply_markup=markup)
        return
    await _answer_photo_progress(message, ticket_id=result.ticket_id, photo_count=result.photo_count)


async def handle_feedback_utterance(
    *,
    message: Message,
    text: str,
    mediator: RequestMediator,
    expected_input: ExpectedInput,
    expected_field: str | None,
) -> bool:
    """Route idea/problem text. Returns True when this step owned the message."""
    from fitness_bot.service.models.commands.feedback import ChangeFeedbackStatusCommand, StartFeedbackDraftCommand

    assert message.from_user is not None
    if expected_input == ExpectedInput.FEEDBACK_PHOTO:
        from fitness_bot.service.models.commands.feedback import SetFeedbackBodyCommand

        ticket_id = _parse_uuid(expected_field)
        markup = feedback_compose_keyboard(ticket_id) if ticket_id is not None else None
        if ticket_id is None:
            await message.answer("Не вижу черновик. Открой «Есть идея» или «Сообщить о проблеме» ещё раз.")
            return True
        try:
            saved = await mediator.send(
                SetFeedbackBodyCommand(
                    telegram_user_id=message.from_user.id,
                    ticket_id=ticket_id,
                    body=text,
                ),
            )
        except DomainError as exc:
            await message.answer(feedback_error_text(exc), reply_markup=markup)
            return True
        await message.answer(
            "Записал. Если продиктовал и хочешь поправить — пришли текст ещё раз, так точнее. "
            "Картинки можно дослать, до 3 штук, и нажать «Отправить».",
            reply_markup=feedback_compose_keyboard(saved.ticket_id),
        )
        return True

    if expected_input == ExpectedInput.FEEDBACK_TEXT:
        kind = _parse_kind_value(expected_field)
        if kind is None:
            await message.answer(
                "Не вижу, к какому черновику это отнести. Открой «Есть идея» или «Сообщить о проблеме» ещё раз.",
            )
            return True
        try:
            draft = await mediator.send(
                StartFeedbackDraftCommand(
                    telegram_user_id=message.from_user.id,
                    kind=kind,
                    body=text,
                ),
            )
        except DomainError as exc:
            await message.answer(feedback_error_text(exc))
            return True
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=message.from_user.id,
                expected_input=ExpectedInput.FEEDBACK_PHOTO,
                expected_field=_compose_field(kind, draft.ticket_id),
            ),
        )
        await message.answer(_COPY[kind]["photos"], reply_markup=feedback_compose_keyboard(draft.ticket_id))
        return True

    if expected_input == ExpectedInput.FEEDBACK_CANCEL_REPLY:
        ticket_id = _parse_uuid(expected_field)
        if ticket_id is None:
            await message.answer("Не нашёл сообщение, которое нужно отменить. Открой список ещё раз.")
            return True
        try:
            result = await mediator.send(
                ChangeFeedbackStatusCommand(
                    telegram_user_id=message.from_user.id,
                    ticket_id=ticket_id,
                    status=FeedbackStatus.CANCELLED,
                    reply=text,
                ),
            )
        except DomainError as exc:
            await message.answer(feedback_error_text(exc))
            return True
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=message.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        await notify_feedback_status(bot=message.bot, result=result)
        await message.answer("Отменил и отправил автору твой ответ, чтобы он понимал, почему так.")
        return True

    return False


def _compose_field(kind: FeedbackKind, ticket_id: UUID) -> str:
    return f"{kind.value}:{ticket_id}"


def _parse_kind_value(raw: str | None) -> FeedbackKind | None:
    if raw is None:
        return None
    head = raw.split(":", 1)[0]
    try:
        return FeedbackKind(head)
    except ValueError:
        return None


def _parse_uuid(raw: str | None) -> UUID | None:
    if not raw:
        return None
    token = raw.split(":", 1)[-1]
    try:
        return UUID(token)
    except ValueError:
        return None
