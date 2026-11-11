"""Start the next training week from a widget bubble."""

from __future__ import annotations

from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.widgets.frame import WidgetFrame, WidgetScreenId, menu_height
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.state import pack_state, read_state
from fitness_bot.service.models.commands.program import GenerateNextWeekCommand


async def start_next_week(ctx: ScreenContext, frame: WidgetFrame) -> ScreenResult:
    try:
        result = await ctx.mediator.send(GenerateNextWeekCommand(telegram_user_id=ctx.user_id))
    except DomainError:
        return _failed(frame, "Не вышло собрать неделю")
    if getattr(result, "agent_unavailable", False):
        return _failed(frame, "Помощник сейчас недоступен")
    if getattr(result, "schema_failed", False) or getattr(result, "document", None) is None:
        return _failed(frame, "Не разобрал ответ — попробуй ещё")
    return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.WEEK)


def _failed(frame: WidgetFrame, note: str) -> ScreenResult:
    data = read_state(frame.chat_data)
    data["hint"] = note[:80]
    updated = WidgetFrame(
        screen=frame.screen,
        chat_data=pack_state(data),
        caption=frame.caption,
        shell_id=frame.shell_id,
        height=menu_height(data) if frame.screen is WidgetScreenId.MENU else frame.height,
    )
    return ScreenResult(frame=updated, answer=updated.chat_data)
