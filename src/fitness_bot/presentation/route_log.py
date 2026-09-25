from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from aiogram import Dispatcher
from aiogram.types import Update

_LOGIN: ContextVar[str] = ContextVar("tg_login", default="-")
_ROUTE: ContextVar[str] = ContextVar("tg_route", default="-")

# Checked before plain text so a photo or voice is not logged as "text".
_MEDIA_ROUTES = (
    ("photo", "photo"),
    ("voice", "voice"),
    ("video", "video"),
    ("video_note", "video_note"),
    ("document", "document"),
    ("sticker", "sticker"),
    ("audio", "audio"),
    ("animation", "animation"),
)


@contextmanager
def telegram_route(*, login: str, route: str) -> Iterator[None]:
    """Bind telegram login and route acronym to every log emitted in the block."""
    login_token: Token[str] = _LOGIN.set(login)
    route_token: Token[str] = _ROUTE.set(route)
    try:
        yield
    finally:
        _ROUTE.reset(route_token)
        _LOGIN.reset(login_token)


class RouteContextFilter(logging.Filter):
    """Prefix log lines with the active telegram login and route acronym."""

    def filter(self, record: logging.LogRecord) -> bool:
        login = _LOGIN.get()
        route = _ROUTE.get()
        if login == "-" and route == "-":
            record.tg_ctx = ""
        else:
            record.tg_ctx = f"[{login} {route}] "
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(tg_ctx)s%(message)s"))
    handler.addFilter(RouteContextFilter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def telegram_login(update: Update) -> str:
    user = _actor(update)
    if user is None:
        return "-"
    username = getattr(user, "username", None)
    if username:
        return f"@{username}"
    user_id = getattr(user, "id", None)
    if user_id is None:
        return "-"
    return f"id:{user_id}"


def route_acronym(update: Update) -> str:
    """Short route id: callback data before ':', a command name, or a message kind."""
    try:
        event = update.event
        event_type = update.event_type
    except LookupError:
        return "-"
    if event_type == "callback_query":
        data = getattr(event, "data", None) or ""
        head = data.split(":", 1)[0].strip()
        return head or "callback"
    text = getattr(event, "text", None) or ""
    if text.startswith("/"):
        command = text.split(maxsplit=1)[0].split("@", 1)[0]
        name = command.lstrip("/")
        return name or "cmd"
    for attr, acronym in _MEDIA_ROUTES:
        if getattr(event, attr, None):
            return acronym
    if text or getattr(event, "caption", None):
        return "text"
    return event_type


def install_update_route_logging(dispatcher: Dispatcher) -> None:
    """Open ``telegram_route`` around every update, including aiogram's own log line.

    Polling logs the duration inside ``feed_update`` and the failure in the caller.
    Both entry points are wrapped so those lines see the same login and route.
    """
    for name in ("feed_update", "_process_update", "_feed_webhook_update"):
        original = getattr(dispatcher, name, None)
        if not callable(original):
            continue
        setattr(dispatcher, name, _observed(original))


def _observed(original: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        update = _update_from_call(args, kwargs)
        login = telegram_login(update) if update is not None else "-"
        route = route_acronym(update) if update is not None else "-"
        with telegram_route(login=login, route=route):
            return await original(*args, **kwargs)

    return wrapped


def _update_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Update | None:
    candidate = kwargs.get("update")
    if isinstance(candidate, Update):
        return candidate
    for arg in args:
        if isinstance(arg, Update):
            return arg
    return None


def _actor(update: Update) -> Any:
    try:
        event = update.event
    except LookupError:
        return None
    return getattr(event, "from_user", None) or getattr(event, "user", None)
