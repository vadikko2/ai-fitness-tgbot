"""Short home bubble: today's workout, repeat, another day, and start."""

from __future__ import annotations

from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.keyboards import WEEKDAY_LABELS
from fitness_bot.presentation.widgets.alt_day import put_alternative
from fitness_bot.presentation.widgets.frame import WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.next_week import start_next_week
from fitness_bot.presentation.widgets.opcodes import OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.shell import WidgetShell
from fitness_bot.presentation.widgets.state import PHASE_ERROR, pack_state, read_state
from fitness_bot.service.models.commands.session import StartSessionFromTemplateCommand, StartTodayWorkoutCommand
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery

_BLOCKED = {
    "rest": "Выходной",
    "no_program": "Нет активной программы",
    "already_done": "Сегодня тренировка уже сделана",
}
_MODES = frozenset({"go", "live", "again", "rest", "none"})


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
        if parsed.name == "go":
            data = read_state(frame.chat_data)
            if (
                data.get("weekDone")
                and str(data.get("mode") or "") == "rest"
                and not isinstance(data.get("altDay"), int)
            ):
                return await start_next_week(ctx, frame)
            return await self._start(ctx, frame, weekday=None)
        if parsed.name == "again":
            return await self._repeat(ctx, frame)
        if parsed.name == "day" and parsed.arg is not None:
            return await self._start(ctx, frame, weekday=int(parsed.arg))
        if parsed.name == "menu":
            return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.MENU)
        return ScreenResult(frame=frame, answer=PHASE_ERROR)

    async def _start(self, ctx: ScreenContext, frame: WidgetFrame, *, weekday: int | None) -> ScreenResult:
        try:
            result = await ctx.mediator.send(
                StartTodayWorkoutCommand(telegram_user_id=ctx.user_id, weekday=weekday),
            )
        except DomainError:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        outcome = str(getattr(result, "outcome", "") or "")
        if outcome in {"started", "resumed"}:
            return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.CONSOLE)
        data = read_state(frame.chat_data)
        data["title"] = _BLOCKED.get(outcome, data.get("title") or "Сегодня")
        if outcome == "already_done":
            data["mode"] = "again"
        elif outcome == "rest":
            data["mode"] = "rest"
        elif outcome == "no_program":
            data["mode"] = "none"
        day = getattr(result, "weekday", None)
        if isinstance(day, int):
            data["day"] = day
        put_alternative(data, result, again=outcome == "already_done")
        updated = self._frame(data)
        return ScreenResult(frame=updated, answer=updated.chat_data)

    async def _repeat(self, ctx: ScreenContext, frame: WidgetFrame) -> ScreenResult:
        data = read_state(frame.chat_data)
        raw_day = data.get("day")
        weekday = raw_day if isinstance(raw_day, int) and 1 <= raw_day <= 7 else None
        try:
            result = await ctx.mediator.send(
                StartSessionFromTemplateCommand(
                    telegram_user_id=ctx.user_id,
                    overwrite_completed=True,
                    weekday=weekday,
                ),
            )
        except DomainError:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        if getattr(result, "document", None) is None:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.CONSOLE)

    def _frame(self, data: dict[str, object]) -> WidgetFrame:
        return WidgetFrame(
            screen=WidgetScreenId.HOME,
            chat_data=pack_state(data),
            caption="",
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
    mode = "go"
    if screen == "session":
        mode = "live"
    elif screen == "no_program":
        mode = "none"
    elif screen == "rest":
        mode = "rest"
        title = "Выходной"
    elif getattr(today, "completed_today", False):
        mode = "again"
        title = _BLOCKED["already_done"]
    if mode not in _MODES:
        mode = "go"
    data: dict[str, object] = {
        "title": title[:48],
        "when": when,
        "streak": len(completed),
        "mode": mode,
    }
    if isinstance(weekday, int):
        data["day"] = weekday
    put_alternative(data, today, again=mode == "again")
    if getattr(today, "week_finished", False):
        data["weekDone"] = 1
    return data
