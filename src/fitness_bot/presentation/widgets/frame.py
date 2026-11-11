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
    MENU = "menu"


# Logical-pixel anchors. Width is always 0 (the bubble's own width) and lives on the transport.
WIDGET_HEIGHT: dict[WidgetScreenId, int] = {
    WidgetScreenId.CONSOLE: 480,
    WidgetScreenId.INTAKE: 420,
    WidgetScreenId.WEEK: 480,
    WidgetScreenId.HOME: 220,
    WidgetScreenId.SUMMARY: 300,
    WidgetScreenId.MENU: 360,
}


@dataclass(frozen=True, slots=True)
class WidgetFrame:
    screen: WidgetScreenId
    chat_data: str
    caption: str
    shell_id: str
    height: int | None = None


def widget_height(frame: WidgetFrame) -> int:
    if frame.height is not None:
        return frame.height
    return WIDGET_HEIGHT[frame.screen]


def menu_height(data: dict[str, object]) -> int:
    """Fit the menu bubble to the hero + visible buttons; no tall empty card."""
    total = 24  # body + wrap padding
    total += 128  # hero with coach chip
    if data.get("mode") == "rest" or data.get("goal") or data.get("weekDone"):
        total += 26
    buttons = 1  # profile
    if data.get("weekDone"):
        buttons += 1
    show_train = not (str(data.get("mode") or "") == "rest" and not data.get("cta"))
    if show_train:
        buttons += 1
        total += 10  # long CTA may wrap
    if data.get("cab") != "cab":
        buttons += 1
    if data.get("mod"):
        buttons += 1
    total += buttons * 52 + max(0, buttons - 1) * 8
    if data.get("hint"):
        total += 28
    return min(520, max(220, total))


def home_height(data: dict[str, object]) -> int:
    """Fit the home bubble to note + one or two actions."""
    total = 78  # chrome header + paddings
    if data.get("streak") not in (None, 0, "0"):
        total += 24
    if data.get("hint"):
        total += 28
    mode = str(data.get("mode") or "go")
    has_alt = bool(data.get("alt") and data.get("altDay"))
    fresh = bool(data.get("weekDone") and mode == "rest" and not has_alt)
    show_note = mode in {"again", "live", "rest", "none"} or bool(data.get("weekDone"))
    if show_note:
        total += 58
    buttons = 1  # menu
    if mode == "rest" and has_alt:
        buttons += 1
    elif has_alt:
        buttons += 1 + (0 if mode == "none" else 1)
    elif fresh or (mode not in {"rest", "none"}):
        buttons += 1
    total += buttons * 50 + max(0, buttons - 1) * 10
    return min(360, max(180, total))


def week_height(data: dict[str, object]) -> int:
    """Fit the week-draft bubble; keep approve above the fold."""
    # chrome header + body pad + lead + day bar + approve + section label
    total = 210
    slots = list(data.get("slots") or [])
    total += max(1, len(slots)) * 48
    if data.get("more") is not None:
        total += 42
    if slots:
        total += 88  # selected-exercise actions
    alts = list(data.get("alts") or [])
    if alts:
        total += 12 + len(alts) * 48
    if data.get("note"):
        total += 28
    return min(700, max(320, total))


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
