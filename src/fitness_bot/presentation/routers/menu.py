from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from jinja2 import Environment

from fitness_bot.presentation.keyboards import stub_later_keyboard


def create_menu_router(*, jinja_env: Environment) -> Router:
    router = Router(name="menu")

    @router.callback_query(F.data == "nutr")
    async def handle_stub(callback: CallbackQuery) -> None:
        text = jinja_env.get_template("stub_later.j2").render()
        if callback.message:
            await callback.message.answer(text, reply_markup=stub_later_keyboard())
        await callback.answer()

    return router
