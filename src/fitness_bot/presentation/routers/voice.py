from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.presentation.routers.text import handle_user_utterance, voice_input_allowed
from fitness_bot.service.models.queries.users import GetWorkflowQuery
from fitness_bot.service.ports.speech_to_text import SpeechToText

logger = logging.getLogger(__name__)


def create_voice_router(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    speech_to_text: SpeechToText,
) -> Router:
    router = Router(name="voice")

    @router.message(F.voice)
    async def handle_tg_voice(message: Message, bot: Bot) -> None:
        assert message.from_user is not None
        if message.voice is None:
            await message.answer("Не удалось разобрать голосовое. Напиши текстом.")
            return

        workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=message.from_user.id))
        if workflow.expected_input == ExpectedInput.NONE:
            await message.answer("Открой нужный раздел через меню.")
            return
        if not voice_input_allowed(
            expected_input=workflow.expected_input,
            expected_field=workflow.expected_field,
        ):
            await message.answer("Голосом здесь можно только свободный текст. Для числа напиши цифрами.")
            return

        try:
            tg_file = await bot.get_file(message.voice.file_id)
            if tg_file.file_path is None:
                await message.answer("Не удалось скачать голосовое. Напиши текстом.")
                return
            buffer = await bot.download_file(tg_file.file_path)
            if buffer is None:
                await message.answer("Не удалось скачать голосовое. Напиши текстом.")
                return
            audio = buffer.read()
        except Exception:
            logger.exception("failed to download telegram voice")
            await message.answer("Не удалось скачать голосовое. Напиши текстом.")
            return

        if not audio:
            await message.answer("Пустое голосовое. Напиши текстом или продиктуй ещё раз.")
            return

        content_type = message.voice.mime_type or "audio/ogg"
        try:
            transcript = await speech_to_text.transcribe(audio=audio, content_type=content_type)
        except NotImplementedError:
            await message.answer("Распознавание речи не настроено. Напиши текстом или задай SHERPA_MODEL_DIR.")
            return
        except Exception:
            logger.exception("speech-to-text failed")
            await message.answer("Не удалось распознать голос. Напиши текстом или попробуй ещё раз.")
            return

        transcript = (transcript or "").strip()
        if not transcript:
            await message.answer("Не разобрал речь. Напиши текстом или продиктуй чётче.")
            return

        await handle_user_utterance(
            message=message,
            text=transcript,
            jinja_env=jinja_env,
            mediator=mediator,
        )

    return router
