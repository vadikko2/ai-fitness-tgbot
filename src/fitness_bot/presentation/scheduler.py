from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput, WeightSource
from fitness_bot.presentation.routers.progress_photo import send_angle_prompt
from fitness_bot.service.models.commands.body import (
    MarkProgressPhotoReminderSentCommand,
    MarkWeightReminderSentCommand,
    StartProgressPhotoCaptureCommand,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.body import (
    ListDueProgressPhotoRemindersQuery,
    ListDueWeightRemindersQuery,
)

logger = logging.getLogger(__name__)


async def handle_wt_tick(*, bot: Bot, mediator: RequestMediator, jinja_env: Environment) -> None:
    due = await mediator.send(ListDueWeightRemindersQuery())
    for item in due.items:
        await handle_wt_ask(bot=bot, mediator=mediator, jinja_env=jinja_env, item=item)


async def handle_wt_ask(*, bot: Bot, mediator: RequestMediator, jinja_env: Environment, item) -> None:
    text = jinja_env.get_template("weight_prompt.j2").render()
    await bot.send_message(chat_id=item.chat_id, text=text)
    await mediator.send(
        ExpectInputCommand(
            telegram_user_id=item.telegram_user_id,
            expected_input=ExpectedInput.WEIGHT,
        ),
    )
    await mediator.send(
        MarkWeightReminderSentCommand(user_id=item.user_id, sent_on=item.local_date),
    )


async def handle_pp_tick(*, bot: Bot, mediator: RequestMediator, jinja_env: Environment) -> None:
    due = await mediator.send(ListDueProgressPhotoRemindersQuery())
    for item in due.items:
        await handle_pp_ask(bot=bot, mediator=mediator, jinja_env=jinja_env, item=item)


async def handle_pp_ask(*, bot: Bot, mediator: RequestMediator, jinja_env: Environment, item) -> None:
    result = await mediator.send(
        StartProgressPhotoCaptureCommand(telegram_user_id=item.telegram_user_id),
    )
    intro = jinja_env.get_template("progress_photo_intro.j2").render(resumed=result.resumed)
    await bot.send_message(chat_id=item.chat_id, text=intro)
    await send_angle_prompt(
        bot=bot,
        chat_id=item.chat_id,
        jinja_env=jinja_env,
        mediator=mediator,
        telegram_user_id=item.telegram_user_id,
        angle=result.next_angle,
    )
    await mediator.send(
        MarkProgressPhotoReminderSentCommand(user_id=item.user_id, sent_on=item.local_date),
    )


async def run_weight_reminder_scheduler(*, bot: Bot, mediator: RequestMediator, jinja_env: Environment) -> None:
    while True:
        try:
            await handle_wt_tick(bot=bot, mediator=mediator, jinja_env=jinja_env)
            await handle_pp_tick(bot=bot, mediator=mediator, jinja_env=jinja_env)
        except Exception:
            logger.exception("reminder tick failed")
        await asyncio.sleep(60)


_ = WeightSource
