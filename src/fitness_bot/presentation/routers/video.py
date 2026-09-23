from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.workout.technique_video import MAX_TECHNIQUE_VIDEO_BYTES
from fitness_bot.presentation.keyboards import session_card_keyboard
from fitness_bot.presentation.routers.session import _document_view, _load_exercise_names, _session_card_markup
from fitness_bot.service.models.commands.session import SaveTechniqueVideoCommand
from fitness_bot.service.models.queries.users import GetWorkflowQuery


def create_video_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="video")

    @router.message(
        F.video | F.video_note | (F.document & F.document.mime_type.startswith("video/")),
    )
    async def handle_tg_video(message: Message, bot: Bot) -> None:
        assert message.from_user is not None
        telegram_user_id = message.from_user.id
        workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=telegram_user_id))
        if workflow.expected_input != ExpectedInput.TECHNIQUE_VIDEO:
            await message.answer("Сейчас видео не ожидается. Открой упражнение в тренировке.")
            return

        file_id: str | None = None
        content_type = "video/mp4"
        reported_size: int | None = None
        if message.video is not None:
            file_id = message.video.file_id
            content_type = message.video.mime_type or "video/mp4"
            reported_size = message.video.file_size
        elif message.video_note is not None:
            file_id = message.video_note.file_id
            content_type = "video/mp4"
            reported_size = message.video_note.file_size
        elif message.document is not None:
            mime = (message.document.mime_type or "").lower()
            file_id = message.document.file_id
            content_type = mime
            reported_size = message.document.file_size

        if file_id is None:
            await message.answer("Не удалось разобрать видео. Пришли ролик ещё раз.")
            return
        if reported_size is not None and reported_size > MAX_TECHNIQUE_VIDEO_BYTES:
            await message.answer("Видео больше 20 МБ. Сожми файл и пришли снова.")
            return

        try:
            tg_file = await bot.get_file(file_id)
            if tg_file.file_path is None:
                raise DomainError("telegram file path is missing")
            if tg_file.file_size is not None and tg_file.file_size > MAX_TECHNIQUE_VIDEO_BYTES:
                await message.answer("Видео больше 20 МБ. Сожми файл и пришли снова.")
                return
            buffer = await bot.download_file(tg_file.file_path)
            if buffer is None:
                raise DomainError("failed to download video")
            body = buffer.read()
        except Exception:
            await message.answer("Не удалось скачать видео. Пришли ролик ещё раз.")
            return

        if not body or len(body) > MAX_TECHNIQUE_VIDEO_BYTES:
            await message.answer("Видео больше 20 МБ или пустое. Пришли другой файл.")
            return

        try:
            result = await mediator.send(
                SaveTechniqueVideoCommand(
                    telegram_user_id=telegram_user_id,
                    body=body,
                    content_type=content_type,
                    slot_position=workflow.focus_slot,
                ),
            )
        except DomainError as exc:
            await message.answer(f"Не удалось сохранить видео: {exc}")
            return

        names = await _load_exercise_names(mediator)
        card = jinja_env.get_template("session_card.j2").render(document=_document_view(result.document, names))
        text = f"Видео упражнения сохранено.\n\n{card}"
        markup = (
            await _session_card_markup(mediator, result.document) if result.document.days else session_card_keyboard()
        )
        await message.answer(text, reply_markup=markup)

    return router
