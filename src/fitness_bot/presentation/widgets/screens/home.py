"""Short home bubble: today's workout, the week streak, and start."""

from __future__ import annotations

from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.keyboards import WEEKDAY_LABELS
from fitness_bot.presentation.widgets.frame import WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.opcodes import OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.shell import WidgetShell
from fitness_bot.presentation.widgets.state import PHASE_ERROR, pack_state, read_state
from fitness_bot.service.models.commands.session import StartTodayWorkoutCommand
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery

_BLOCKED = {
    "rest": "Выходной",
    "no_program": "Нет активной программы",
    "already_done": "Сегодня тренировка уже сделана",
}


class HomeScreen:
    screen_id = WidgetScreenId.HOME

    def __init__(self, shell: WidgetShell) -> None:
        self.shell = shell

    async def open(self, ctx: ScreenContext) -> WidgetFrame:
        today = await ctx.mediator.send(GetTodayWorkoutQuery(telegram_user_id=ctx.user_id))
        return self._frame(_payload(today))

    async def apply(self, ctx: ScreenContext, opcode: str) -> ScreenResult:
        parsed = parse_opcode(opcode)
        frame = ctx.binding.frame or await self.open(ctx)
        if isinstance(parsed, OpcodeRejection) or parsed.screen is not WidgetScreenId.HOME:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        if parsed.name != "go":
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        try:
            result = await ctx.mediator.send(StartTodayWorkoutCommand(telegram_user_id=ctx.user_id))
        except DomainError:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        outcome = str(getattr(result, "outcome", "") or "")
        if outcome in {"started", "resumed"}:
            return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.CONSOLE)
        data = read_state(frame.chat_data)
        data["title"] = _BLOCKED.get(outcome, data.get("title") or "Сегодня")
        updated = self._frame(data)
        return ScreenResult(frame=updated, answer=updated.chat_data)

    def _frame(self, data: dict[str, object]) -> WidgetFrame:
        title = str(data.get("title") or "Сегодня")
        when = str(data.get("when") or "")
        streak = data.get("streak")
        caption = f"▶️ {title}."
        if when:
            caption = f"{caption} {when}."
        if streak:
            caption = f"{caption} Серия {streak}."
        return WidgetFrame(
            screen=WidgetScreenId.HOME,
            chat_data=pack_state(data),
            caption=caption,
            shell_id="home",
        )


def _payload(today: object) -> dict[str, object]:
    document = getattr(today, "document", None)
    screen = str(getattr(today, "screen", "") or "")
    title = "Сегодня"
    if document is not None and getattr(document, "days", None):
        title = str(document.days[0].title)
    elif screen == "rest":
        title = "Выходной"
    elif screen == "no_program":
        title = "Нет программы"
    weekday = getattr(today, "weekday", None)
    when = WEEKDAY_LABELS.get(weekday, "") if isinstance(weekday, int) else ""
    completed = list(getattr(today, "completed_weekdays", []) or [])
    return {"title": title[:48], "when": when, "streak": len(completed)}
