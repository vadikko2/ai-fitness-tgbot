"""Screen contract. Concrete console, intake, week, and home screens are not part of this layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cqrs import RequestMediator

from fitness_bot.presentation.widgets.frame import WidgetBinding, WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.shell import WidgetShell
from fitness_bot.service.models.commands.users import ExpectInputCommand


@dataclass(frozen=True, slots=True)
class ScreenContext:
    user_id: int
    binding: WidgetBinding
    mediator: RequestMediator


@dataclass(frozen=True, slots=True)
class ScreenResult:
    frame: WidgetFrame
    answer: str | None
    expect: ExpectInputCommand | None = None
    video_file_id: str | None = None
    clear_video: bool = False
    cover_file_id: str | None = None
    photo_path: str | None = None
    navigate: WidgetScreenId | None = None


class WidgetScreen(Protocol):
    screen_id: WidgetScreenId
    shell: WidgetShell

    async def open(self, ctx: ScreenContext) -> WidgetFrame:
        """First frame from the domain, without writing."""

    async def apply(self, ctx: ScreenContext, opcode: str) -> ScreenResult:
        """Opcode already parsed. An unknown phase returns the previous frame and an error answer."""
