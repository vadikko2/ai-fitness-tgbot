from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from jinja2 import Environment


def create_unsupported_router(*, jinja_env: Environment) -> Router:
    """Reject attachments outside text / voice / photo / video (incl. video/* files)."""
    router = Router(name="unsupported")

    @router.message(~F.text.startswith("/"))
    async def handle_unsupported(message: Message) -> None:
        text = jinja_env.get_template("unsupported_attachment.j2").render()
        await message.answer(text)

    return router
