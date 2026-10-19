from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from fitness_bot.presentation.chat_pages import install_chat_pages
from fitness_bot.presentation.health import start_health_server
from fitness_bot.presentation.route_log import configure_logging, install_update_route_logging
from fitness_bot.presentation.routers.body import create_body_router
from fitness_bot.presentation.routers.coach import create_coach_router
from fitness_bot.presentation.routers.feedback import create_feedback_router
from fitness_bot.presentation.routers.history import create_history_router
from fitness_bot.presentation.routers.library import create_library_router
from fitness_bot.presentation.routers.menu import create_menu_router
from fitness_bot.presentation.routers.moderator import create_moderator_router
from fitness_bot.presentation.routers.nutrition import create_nutrition_router
from fitness_bot.presentation.routers.photo import create_photo_router
from fitness_bot.presentation.routers.profile import create_profile_router
from fitness_bot.presentation.routers.program import create_program_router
from fitness_bot.presentation.routers.progress_photo import create_progress_photo_router
from fitness_bot.presentation.routers.session import create_session_router
from fitness_bot.presentation.routers.start import create_start_router
from fitness_bot.presentation.routers.text import create_text_router
from fitness_bot.presentation.routers.training_reminder import create_training_reminder_router
from fitness_bot.presentation.routers.unsupported import create_unsupported_router
from fitness_bot.presentation.routers.video import create_video_router
from fitness_bot.presentation.routers.voice import create_voice_router
from fitness_bot.presentation.routers.wellbeing import create_wellbeing_router
from fitness_bot.presentation.scheduler import run_weight_reminder_scheduler
from fitness_bot.presentation.wiring.container import build_container, build_mediator


async def run() -> None:
    configure_logging()
    container = build_container()
    mediator = build_mediator(container)
    jinja_env = container.jinja_env()
    settings = container.config()
    speech_to_text = container.speech_to_text()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    install_chat_pages(dispatcher, bot)
    install_update_route_logging(dispatcher)
    dispatcher.include_router(create_start_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_profile_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_body_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_progress_photo_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_history_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_program_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_library_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_coach_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_moderator_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_feedback_router(mediator=mediator))
    dispatcher.include_router(create_session_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_training_reminder_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_wellbeing_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_nutrition_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(create_menu_router(jinja_env=jinja_env))
    dispatcher.include_router(create_video_router(jinja_env=jinja_env, mediator=mediator))
    dispatcher.include_router(
        create_photo_router(
            jinja_env=jinja_env,
            mediator=mediator,
            object_storage=container.object_storage(),
        ),
    )
    dispatcher.include_router(
        create_voice_router(jinja_env=jinja_env, mediator=mediator, speech_to_text=speech_to_text),
    )
    dispatcher.include_router(create_text_router(jinja_env=jinja_env, mediator=mediator))
    # Last: stickers, audio files, non-video docs, location, contacts, etc.
    dispatcher.include_router(create_unsupported_router(jinja_env=jinja_env))
    scheduler_task = asyncio.create_task(
        run_weight_reminder_scheduler(bot=bot, mediator=mediator, jinja_env=jinja_env),
    )
    async with start_health_server(settings.health_host, settings.health_port):
        try:
            await dispatcher.start_polling(bot)
        finally:
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task
            await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
