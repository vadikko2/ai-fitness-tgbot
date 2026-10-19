"""One screen of chat messages per user, dropped when they open another screen.

The bot is a single polling process, so the current page lives in memory.
Only ids recorded for that page are deleted. Older history is left alone.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message

DELETE_PAUSE_SECONDS = 0.05

# Edits of the message that is already on screen. A new bubble here stays on the
# same page; it must not wipe the screen the user is still using.
_SAME_PAGE_PREFIXES = (
    "slot_plan:",
    "slot_undo:",
    "slot_fact:",
    "slot_w_",
    "slot_r_",
    "slot_alt:",
    "slot_swap",
    "slot_card:",
    "slot_how:",
    "slot_video:",
    "pdraft_edit:",
    "pdraft_w_",
    "pdraft_r_",
)

_OUTGOING = (
    "answer",
    "answer_photo",
    "answer_video",
    "answer_animation",
    "answer_document",
    "answer_voice",
    "answer_media_group",
)

_BOT_SENDS = (
    "send_message",
    "send_photo",
    "send_video",
    "send_animation",
    "send_document",
    "send_voice",
)

# user id -> [(chat id, message id)] in send order
_pages: dict[int, list[tuple[int, int]]] = {}
_locks: dict[int, asyncio.Lock] = {}


def _set(obj: object, name: str, value: object) -> None:
    """Aiogram models are frozen; tests use plain objects. Both accept this."""
    object.__setattr__(obj, name, value)


def reset_chat_pages() -> None:
    """Drop tracked ids. Tests use this so one case cannot leak into the next."""
    _pages.clear()
    _locks.clear()


def page_message_ids(user_id: int) -> list[int]:
    return [message_id for _chat_id, message_id in _pages.get(user_id, [])]


def stays_on_page(callback_data: str | None) -> bool:
    """True when the tap edits the current screen instead of opening another one."""
    if not callback_data:
        return False
    return any(callback_data.startswith(prefix) for prefix in _SAME_PAGE_PREFIXES)


def remember(user_id: int, chat_id: int, message_id: int) -> None:
    page = _pages.setdefault(user_id, [])
    ref = (chat_id, message_id)
    if ref not in page:
        page.append(ref)


def remember_incoming(message: object) -> None:
    """Keep a user reply (typed weight, reps, and other answers) on the current page."""
    user = getattr(message, "from_user", None)
    user_id = getattr(user, "id", None)
    message_id = getattr(message, "message_id", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if user_id is None or message_id is None or chat_id is None:
        return
    remember(int(user_id), int(chat_id), int(message_id))


def remember_sent(sent: object, *, user_id: int | None = None) -> None:
    if isinstance(sent, list | tuple):
        for item in sent:
            remember_sent(item, user_id=user_id)
        return
    message_id = getattr(sent, "message_id", None)
    chat = getattr(sent, "chat", None)
    chat_id = getattr(chat, "id", None)
    if message_id is None or chat_id is None:
        return
    key = int(chat_id if user_id is None else user_id)
    remember(key, int(chat_id), int(message_id))


def _lock(user_id: int) -> asyncio.Lock:
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock


def bot_of(event: object) -> object | None:
    bot = getattr(event, "bot", None)
    if bot is not None:
        return bot
    message = getattr(event, "message", None)
    if message is None:
        return None
    return getattr(message, "bot", None)


async def leave_page(bot: object | None, user_id: int) -> None:
    """Delete every message recorded for this user's current page.

    Failures are ignored: the message may already be gone or older than Telegram allows.
    A short pause between deletes keeps a long page under the flood limit.
    """
    if bot is None or not callable(getattr(bot, "delete_message", None)):
        return
    async with _lock(user_id):
        refs = _pages.pop(user_id, [])
    for index, (chat_id, message_id) in enumerate(refs):
        if index:
            await asyncio.sleep(DELETE_PAUSE_SECONDS)
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            continue


def _guard_callback_answer(callback: object) -> None:
    """Answer the callback once. A later answer, after the message was deleted, is a no-op."""
    if getattr(callback, "_chat_page_answer_guard", False):
        return
    original = callback.answer

    async def guarded(*args: object, **kwargs: object) -> object:
        if getattr(callback, "_chat_page_acked", False):
            return None
        _set(callback, "_chat_page_acked", True)
        return await original(*args, **kwargs)

    _set(callback, "answer", guarded)
    _set(callback, "_chat_page_answer_guard", True)


async def _ack(callback: object) -> None:
    answer = getattr(callback, "answer", None)
    if callable(answer):
        await answer()


def _once(open_page: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
    state = {"done": False}

    async def run() -> None:
        if state["done"]:
            return
        state["done"] = True
        await open_page()

    return run


def _bind_outgoing(
    message: object,
    *,
    user_id: int,
    open_page: Callable[[], Awaitable[None]] | None,
) -> None:
    if message is None or getattr(message, "_chat_page_outgoing", False):
        return
    opener = _once(open_page) if open_page is not None else None
    for name in _OUTGOING:
        original = getattr(message, name, None)
        if not callable(original):
            continue
        _set(message, name, _track_outgoing(original, user_id=user_id, opener=opener))
    _set(message, "_chat_page_outgoing", True)


def _track_outgoing(
    original: Callable[..., Awaitable[object]],
    *,
    user_id: int,
    opener: Callable[[], Awaitable[None]] | None,
) -> Callable[..., Awaitable[object]]:
    async def wrapped(*args: object, **kwargs: object) -> object:
        if opener is not None:
            await opener()
        sent = await original(*args, **kwargs)
        remember_sent(sent, user_id=user_id)
        return sent

    return wrapped


def _looks_like_callback(event: object) -> bool:
    """Callback queries and the fakes tests use. A chat message has no callback data."""
    return (
        callable(getattr(event, "answer", None))
        and hasattr(event, "data")
        and getattr(event, "message", None) is not None
    )


def _looks_like_message(event: object) -> bool:
    return (
        callable(getattr(event, "answer", None))
        and getattr(event, "from_user", None) is not None
        and not hasattr(event, "data")
    )


def _open_callback(callback: object, user_id: int) -> Callable[[], Awaitable[None]]:
    async def open_page() -> None:
        # Acknowledge while the tapped message still exists, then drop the previous page.
        await _ack(callback)
        await leave_page(bot_of(callback), user_id)

    return open_page


def _open_command(message: object, user_id: int) -> Callable[[], Awaitable[None]]:
    async def open_page() -> None:
        await leave_page(bot_of(message), user_id)

    return open_page


def _prepare_callback(callback: object) -> None:
    user = getattr(callback, "from_user", None)
    message = getattr(callback, "message", None)
    if user is None or message is None or getattr(user, "id", None) is None:
        return
    _guard_callback_answer(callback)
    user_id = int(user.id)
    opener = None if stays_on_page(getattr(callback, "data", None)) else _open_callback(callback, user_id)
    _bind_outgoing(message, user_id=user_id, open_page=opener)


def _prepare_message(message: object) -> None:
    user = getattr(message, "from_user", None)
    if user is None or getattr(user, "id", None) is None:
        return
    user_id = int(user.id)
    text = getattr(message, "text", None) or ""
    opener = _open_command(message, user_id) if str(text).startswith("/") else None
    _bind_outgoing(message, user_id=user_id, open_page=opener)


def _wrap_bot_send(original: Callable[..., Awaitable[object]]) -> Callable[..., Awaitable[object]]:
    async def wrapped(*args: object, **kwargs: object) -> object:
        sent = await original(*args, **kwargs)
        remember_sent(sent)
        return sent

    return wrapped


def bind_bot(bot: Bot) -> None:
    """Record messages the scheduler and other bot.send_* calls push into a chat."""
    if getattr(bot, "_chat_page_bound", False):
        return
    for name in _BOT_SENDS:
        original = getattr(bot, name, None)
        if not callable(original):
            continue
        _set(bot, name, _wrap_bot_send(original))
    _set(bot, "_chat_page_bound", True)


class ChatPageMiddleware(BaseMiddleware):
    """Track outgoing bubbles. Navigation sends replace the previous page."""

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        if _looks_like_callback(event):
            _prepare_callback(event)
        elif isinstance(event, Message) or _looks_like_message(event):
            _prepare_message(event)
        return await handler(event, data)


def install_chat_pages(dispatcher: Any, bot: Bot) -> None:
    middleware = ChatPageMiddleware()
    dispatcher.callback_query.middleware(middleware)
    dispatcher.message.middleware(middleware)
    bind_bot(bot)
