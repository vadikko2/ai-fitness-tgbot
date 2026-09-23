from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.domain.errors import DomainError
from fitness_bot.service.models.commands.coach import (
    RecordModeratorApplicationMessageCommand,
    SubmitCoachApplicationCommand,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.users import GetWorkflowQuery
from fitness_bot.service.ports.object_storage import ObjectStorage


def _mod_kb(application_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve", callback_data=f"mod_c_ok:{application_id}"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"mod_c_no:{application_id}"),
            ],
        ],
    )


async def _submit_credential(
    *,
    message: Message,
    mediator: RequestMediator,
    object_storage: ObjectStorage,
    body: bytes,
    content_type: str,
) -> None:
    assert message.from_user is not None
    workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=message.from_user.id))
    if workflow.expected_input != ExpectedInput.COACH_CREDENTIAL:
        text = "Сейчас файл подтверждения не ожидается."
        await message.answer(text)
        return
    name, _, rest = (workflow.expected_field or "").partition("|")
    bio, _, portfolio = rest.partition("|")
    if not name.strip() or not portfolio.strip():
        await message.answer("Сначала заполните шаги 1/3 и 2/3 заявки.")
        return
    key = f"users/{workflow.user_id}/coach/credentials/pending"
    await object_storage.put(key, body, content_type)
    try:
        result = await mediator.send(
            SubmitCoachApplicationCommand(
                telegram_user_id=message.from_user.id,
                display_name=name.strip(),
                bio=bio.strip() or name.strip(),
                portfolio_url=portfolio.strip(),
                credential_object_key=key,
                credential_content_type=content_type,
                credential_byte_size=len(body),
                credential_caption=message.caption,
            ),
        )
    except DomainError as exc:
        await message.answer(str(exc))
        return
    await mediator.send(
        ExpectInputCommand(
            telegram_user_id=message.from_user.id,
            expected_input=ExpectedInput.NONE,
        ),
    )
    text = f"Новая заявка на статус тренера\n{result.display_name}\n{result.bio}\nПортфолио: {result.portfolio_url}"
    kb = _mod_kb(result.application_id)
    for chat in result.moderator_chats:
        chat_id = chat.get("chat_id")
        mod_user_id = chat.get("user_id")
        if chat_id is None or mod_user_id is None:
            continue
            try:
                sent = await message.bot.send_message(chat_id, text, reply_markup=kb)
                media_id = None
                try:
                    if message.photo:
                        media = await message.bot.send_photo(chat_id, message.photo[-1].file_id)
                        media_id = media.message_id
                    elif message.document is not None:
                        media = await message.bot.send_document(chat_id, message.document.file_id)
                        media_id = media.message_id
                except Exception:
                    media_id = None
                await mediator.send(
                    RecordModeratorApplicationMessageCommand(
                        application_id=result.application_id,
                        moderator_user_id=UUID(str(mod_user_id)),
                        chat_id=chat_id,
                        message_id=sent.message_id,
                        media_message_id=media_id,
                    ),
                )
            except Exception:
                continue
    mods = len(result.moderator_user_ids)
    await message.answer(
        f"Заявка 3/3 отправлена модераторам ({mods}). Обычно ответ за 1–2 дня.",
    )


def create_photo_router(
    *,
    jinja_env: Environment,
    mediator: RequestMediator | None = None,
    object_storage: ObjectStorage | None = None,
) -> Router:
    router = Router(name="photo")

    @router.message(F.photo)
    async def handle_tg_photo(message: Message) -> None:
        if mediator is None or object_storage is None or message.from_user is None:
            text = jinja_env.get_template("photo_not_expected.j2").render()
            await message.answer(text)
            return
        workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=message.from_user.id))
        if workflow.expected_input != ExpectedInput.COACH_CREDENTIAL:
            text = jinja_env.get_template("photo_not_expected.j2").render()
            await message.answer(text)
            return
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        assert file.file_path is not None
        buf = await message.bot.download_file(file.file_path)
        body = buf.read() if hasattr(buf, "read") else bytes(buf)
        await _submit_credential(
            message=message,
            mediator=mediator,
            object_storage=object_storage,
            body=body,
            content_type="image/jpeg",
        )

    @router.message(F.document)
    async def handle_tg_document(message: Message) -> None:
        from aiogram.dispatcher.event.bases import SkipHandler

        if mediator is None or object_storage is None or message.from_user is None or message.document is None:
            raise SkipHandler()
        workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=message.from_user.id))
        if workflow.expected_input != ExpectedInput.COACH_CREDENTIAL:
            raise SkipHandler()
        mime = (message.document.mime_type or "").lower()
        if not (mime.startswith("image/") or mime in {"application/pdf"}):
            await message.answer("Нужно фото/скан или PDF подтверждения.")
            return
        file = await message.bot.get_file(message.document.file_id)
        assert file.file_path is not None
        buf = await message.bot.download_file(file.file_path)
        body = buf.read() if hasattr(buf, "read") else bytes(buf)
        await _submit_credential(
            message=message,
            mediator=mediator,
            object_storage=object_storage,
            body=body,
            content_type=mime or "application/pdf",
        )

    return router
