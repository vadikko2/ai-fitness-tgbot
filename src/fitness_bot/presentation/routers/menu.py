from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from jinja2 import Environment

from fitness_bot.presentation.keyboards import (
    INFO_TOPIC_IDS,
    info_menu_keyboard,
    info_topic_keyboard,
    parse_how_it_works,
    stub_later_keyboard,
)


def create_menu_router(*, jinja_env: Environment) -> Router:
    router = Router(name="menu")

    @router.callback_query(F.data == "nutr")
    async def handle_stub(callback: CallbackQuery) -> None:
        text = jinja_env.get_template("stub_later.j2").render()
        if callback.message:
            await callback.message.answer(text, reply_markup=stub_later_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "info")
    async def handle_info(callback: CallbackQuery) -> None:
        text = jinja_env.get_template("info.j2").render(topic="menu")
        if callback.message:
            await callback.message.answer(text, reply_markup=info_menu_keyboard())
        await callback.answer()

    @router.callback_query(F.data.startswith("info:"))
    async def handle_info_topic(callback: CallbackQuery) -> None:
        topic = (callback.data or "").split(":", 1)[1]
        if topic not in INFO_TOPIC_IDS:
            text = jinja_env.get_template("info.j2").render(topic="menu")
            markup = info_menu_keyboard()
        else:
            text = jinja_env.get_template("info.j2").render(topic=topic)
            markup = info_topic_keyboard()
        if callback.message:
            await callback.message.answer(text, reply_markup=markup)
        await callback.answer()

    @router.callback_query(F.data.startswith("ihow:"))
    async def handle_how_it_works(callback: CallbackQuery) -> None:
        parsed = parse_how_it_works(callback.data or "")
        if parsed is None:
            await callback.answer()
            return
        topic, back = parsed
        text = jinja_env.get_template("info.j2").render(topic=topic)
        if callback.message:
            await callback.message.answer(text, reply_markup=info_topic_keyboard(back=back))
        await callback.answer()

    return router
