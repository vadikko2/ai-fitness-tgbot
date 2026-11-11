"""Pull widget_query fields off an update and hand them to the gateway."""

from __future__ import annotations

from typing import Any

from aiogram import Router
from aiogram.dispatcher.event.telegram import TelegramEventObserver
from aiogram.types import Update

from fitness_bot.presentation.widgets.gateway import WidgetGateway, WidgetQuery

_installed = False
_original_event_type = Update.event_type.fget
_original_event = Update.event.fget


def install_widget_query_routing() -> None:
    """Teach aiogram 3.31, which has no widget_query field, to route that update."""
    global _installed
    if _installed:
        return

    def event_type(self: Update) -> str:
        extra = self.__pydantic_extra__ or {}
        if extra.get("widget_query") is not None:
            return "widget_query"
        return _original_event_type(self)

    def event(self: Update) -> Any:
        extra = self.__pydantic_extra__ or {}
        query = extra.get("widget_query")
        if query is not None:
            return query
        return _original_event(self)

    Update.event_type = property(event_type)  # type: ignore[method-assign, assignment]
    Update.event = property(event)  # type: ignore[method-assign, assignment]
    _installed = True


def extract_widget_query(widget_query: object) -> WidgetQuery | None:
    data = _query_dict(widget_query)
    if data is None:
        return None
    query_id = data.get("id")
    user_id = _field_id(data.get("from"))
    chat_id = _field_id(data.get("chat"))
    message_id = data.get("message_id")
    opcode = data.get("data")
    if not isinstance(query_id, str) or not query_id:
        return None
    if not all(_plain_int(item) is not None for item in (user_id, chat_id, message_id)):
        return None
    if not isinstance(opcode, str) or opcode == "":
        return None
    return WidgetQuery(
        query_id=query_id,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        data=opcode,
    )


def widget_query_id(widget_query: object) -> str | None:
    data = _query_dict(widget_query)
    if data is None:
        return None
    query_id = data.get("id")
    if isinstance(query_id, str) and query_id:
        return query_id
    return None


def create_widget_router(*, gateway: WidgetGateway) -> Router:
    install_widget_query_routing()
    router = Router(name="widget")
    observer = TelegramEventObserver(router=router, event_name="widget_query")
    router.observers["widget_query"] = observer

    @observer()
    async def handle_widget_query(widget_query: object) -> None:
        query = extract_widget_query(widget_query)
        if query is None:
            query_id = widget_query_id(widget_query)
            if query_id is not None:
                await gateway.reject(query_id)
            return
        await gateway.on_query(query)

    return router


def polling_allowed_updates(dispatcher: Router) -> list[str]:
    """Updates this process handles, including widget taps and the current message routes."""
    names = set(dispatcher.resolve_used_update_types())
    names.update(("message", "callback_query", "widget_query"))
    return sorted(names)


def _query_dict(widget_query: object) -> dict[str, Any] | None:
    if isinstance(widget_query, dict):
        return widget_query
    raw = getattr(widget_query, "widget_query", None)
    if isinstance(raw, dict):
        return raw
    if isinstance(widget_query, Update):
        extra = widget_query.__pydantic_extra__ or {}
        nested = extra.get("widget_query")
        if isinstance(nested, dict):
            return nested
    return None


def _plain_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _field_id(value: object) -> object:
    if isinstance(value, dict):
        return value.get("id")
    return getattr(value, "id", None)
