"""One widget bubble: the frame the shell draws, and where that bubble lives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WidgetScreenId(StrEnum):
    CONSOLE = "console"
    INTAKE = "intake"
    WEEK = "week"
    HOME = "home"
    SUMMARY = "summary"


# Logical-pixel anchors. Width is always 0 (the bubble's own width) and lives on the transport.
WIDGET_HEIGHT: dict[WidgetScreenId, int] = {
    WidgetScreenId.CONSOLE: 440,
    WidgetScreenId.INTAKE: 480,
    WidgetScreenId.WEEK: 480,
    WidgetScreenId.HOME: 280,
    WidgetScreenId.SUMMARY: 360,
}


@dataclass(frozen=True, slots=True)
class WidgetFrame:
    screen: WidgetScreenId
    chat_data: str
    caption: str
    shell_id: str


@dataclass(frozen=True, slots=True)
class WidgetBinding:
    chat_id: int
    message_id: int
    screen: WidgetScreenId
    video_message_id: int | None = None
    frame: WidgetFrame | None = None


class WidgetBindings:
    """In-memory bubble ids. The domain stays the source of truth for sets and profile."""

    def __init__(self) -> None:
        self._by_user: dict[int, WidgetBinding] = {}
        self._by_message: dict[tuple[int, int], int] = {}

    def get(self, telegram_user_id: int) -> WidgetBinding | None:
        return self._by_user.get(telegram_user_id)

    def lookup(self, chat_id: int, message_id: int) -> tuple[int, WidgetBinding] | None:
        user_id = self._by_message.get((chat_id, message_id))
        if user_id is None:
            return None
        binding = self._by_user.get(user_id)
        if binding is None:
            return None
        return user_id, binding

    def put(self, telegram_user_id: int, binding: WidgetBinding) -> None:
        previous = self._by_user.get(telegram_user_id)
        if previous is not None:
            self._by_message.pop((previous.chat_id, previous.message_id), None)
        self._by_user[telegram_user_id] = binding
        self._by_message[(binding.chat_id, binding.message_id)] = telegram_user_id

    def clear(self, telegram_user_id: int) -> None:
        previous = self._by_user.pop(telegram_user_id, None)
        if previous is not None:
            self._by_message.pop((previous.chat_id, previous.message_id), None)
