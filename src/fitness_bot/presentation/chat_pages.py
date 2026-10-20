"""One screen of chat messages per user, dropped when they open another screen.

The bot is a single polling process, so the current page lives in memory.
Only ids recorded for that page are deleted. Older history is left alone.

Notifications are not part of that screen. A training nudge, a weigh-in,
a progress-photo ask, and other pushes stay until the user presses a button
on that message, or answers the question it asked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
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


@dataclass
class _Push:
    """Messages of one notification. Navigation does not delete them."""

    user_id: int
    dismiss: str
    refs: list[tuple[int, int]] = field(default_factory=list)


# user id -> notifications still on screen
_pushes: dict[int, list[_Push]] = {}
# (chat id, message id) -> the notification that owns it
_push_by_ref: dict[tuple[int, int], _Push] = {}
_open_push: ContextVar[_Push | None] = ContextVar("open_push", default=None)


def _set(obj: object, name: str, value: object) -> None:
    """Aiogram models are frozen; tests use plain objects. Both accept this."""
    object.__setattr__(obj, name, value)


def reset_chat_pages() -> None:
    """Drop tracked ids. Tests use this so one case cannot leak into the next."""
    _pages.clear()
    _locks.clear()
    _pushes.clear()
    _push_by_ref.clear()


def page_message_ids(user_id: int) -> list[int]:
    return [message_id for _chat_id, message_id in _pages.get(user_id, [])]


def push_message_ids(user_id: int) -> list[int]:
    return [message_id for push in _pushes.get(user_id, []) for _chat_id, message_id in push.refs]


def message_is_push(message: object | None) -> bool:
    """True when this bubble is a notification, not the screen the user has open."""
    if message is None:
        return False
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    message_id = getattr(message, "message_id", None)
    if chat_id is None or message_id is None:
        return False
    return (int(chat_id), int(message_id)) in _push_by_ref


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


def _refs(sent: object) -> list[tuple[int, int]]:
    if isinstance(sent, list | tuple):
        refs: list[tuple[int, int]] = []
        for item in sent:
            refs.extend(_refs(item))
        return refs
    message_id = getattr(sent, "message_id", None)
    chat = getattr(sent, "chat", None)
    chat_id = getattr(chat, "id", None)
    if message_id is None or chat_id is None:
        return []
    return [(int(chat_id), int(message_id))]


def _bind_push(push: _Push, sent: object) -> None:
    refs = _refs(sent)
    if not refs:
        return
    if not push.refs:
        _pushes.setdefault(push.user_id, []).append(push)
    for ref in refs:
        if ref not in push.refs:
            push.refs.append(ref)
            _push_by_ref[ref] = push


@contextmanager
def push_scope(user_id: int, *, dismiss: str = "button") -> Iterator[None]:
    """Messages sent with the bot while this is open stay until the user acts on them.

    ``button`` goes away when they press a button on that message.
    ``weight`` and ``progress_photo`` go away when that ask is answered.
    """
    push = _Push(user_id=int(user_id), dismiss=dismiss)
    token = _open_push.set(push)
    try:
        yield
    finally:
        _open_push.reset(token)


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


async def _delete_push(bot: object | None, push: _Push) -> None:
    listed = _pushes.get(push.user_id, [])
    if push in listed:
        listed.remove(push)
        if not listed:
            _pushes.pop(push.user_id, None)
    refs = list(push.refs)
    push.refs.clear()
    for ref in refs:
        _push_by_ref.pop(ref, None)
    if bot is None or not callable(getattr(bot, "delete_message", None)):
        return
    for index, (chat_id, message_id) in enumerate(refs):
        if index:
            await asyncio.sleep(DELETE_PAUSE_SECONDS)
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            continue


async def dismiss_tapped_push(bot: object | None, message: object | None) -> None:
    """Delete the notification whose button was just pressed. Other pushes stay."""
    if message is None:
        return
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    message_id = getattr(message, "message_id", None)
    if chat_id is None or message_id is None:
        return
    push = _push_by_ref.get((int(chat_id), int(message_id)))
    if push is None:
        return
    await _delete_push(bot, push)


async def dismiss_pushes(bot: object | None, user_id: int, reason: str) -> None:
    """Delete notifications that asked for this answer, now that it was given."""
    for push in list(_pushes.get(user_id, [])):
        if push.dismiss == reason:
            await _delete_push(bot, push)


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
    # A button on a notification only removes that notification. The open screen stays.
    keep_screen = stays_on_page(getattr(callback, "data", None)) or message_is_push(message)
    opener = None if keep_screen else _open_callback(callback, user_id)
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
        push = _open_push.get()
        if push is None:
            remember_sent(sent)
        else:
            _bind_push(push, sent)
        return sent

    return wrapped


def bind_bot(bot: Bot) -> None:
    """Record bot.send_* calls. Inside ``push_scope`` they are a notification, otherwise a screen."""
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
        result = await handler(event, data)
        if _looks_like_callback(event) and not stays_on_page(getattr(event, "data", None)):
            await dismiss_tapped_push(bot_of(event), getattr(event, "message", None))
        return result


def install_chat_pages(dispatcher: Any, bot: Bot) -> None:
    middleware = ChatPageMiddleware()
    dispatcher.callback_query.middleware(middleware)
    dispatcher.message.middleware(middleware)
    bind_bot(bot)
