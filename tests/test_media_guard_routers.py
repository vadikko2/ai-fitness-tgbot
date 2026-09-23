from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fitness_bot.presentation.routers.photo import create_photo_router
from fitness_bot.presentation.routers.unsupported import create_unsupported_router
from fitness_bot.presentation.templates_env import create_jinja_env


@pytest.mark.asyncio
async def test_unsupported_router_rejects_sticker() -> None:
    jinja_env = create_jinja_env()
    router = create_unsupported_router(jinja_env=jinja_env)
    handler = router.message.handlers[0].callback

    message = MagicMock()
    message.answer = AsyncMock()

    await handler(message)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "текст" in text.lower()
    assert "видео" in text.lower()


@pytest.mark.asyncio
async def test_photo_router_says_not_expected() -> None:
    jinja_env = create_jinja_env()
    router = create_photo_router(jinja_env=jinja_env)
    handler = router.message.handlers[0].callback

    message = MagicMock()
    message.answer = AsyncMock()

    await handler(message)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "фото" in text.lower()
