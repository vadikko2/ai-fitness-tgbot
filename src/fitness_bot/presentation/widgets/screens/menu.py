"""Main hub: train, profile, coach — short and calm."""

from __future__ import annotations

from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.flow_helpers import goal_label
from fitness_bot.presentation.keyboards import WEEKDAY_LABELS
from fitness_bot.presentation.widgets.alt_day import put_alternative, resolve_alternative
from fitness_bot.presentation.widgets.frame import WidgetFrame, WidgetScreenId, menu_height
from fitness_bot.presentation.widgets.next_week import start_next_week
from fitness_bot.presentation.widgets.opcodes import OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.shell import WidgetShell
from fitness_bot.presentation.widgets.state import PHASE_ERROR, pack_state, read_state
from fitness_bot.service.models.commands.session import StartTodayWorkoutCommand
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery
from fitness_bot.service.models.queries.users import GetHomeQuery

_HANDOFF = {
    "prof": "profile",
    "cmine": "coach_mine",
    "cfind": "coach_search",
    "cab": "coach_cab",
    "apply": "coach_apply",
    "mod": "mod",
}


class MenuScreen:
    screen_id = WidgetScreenId.MENU

    def __init__(self, shell: WidgetShell) -> None:
        self.shell = shell

    async def open(self, ctx: ScreenContext) -> WidgetFrame:
        home = await ctx.mediator.send(GetHomeQuery(telegram_user_id=ctx.user_id))
        today = await ctx.mediator.send(GetTodayWorkoutQuery(telegram_user_id=ctx.user_id))
        return self._frame(_payload(home, today))

    async def apply(self, ctx: ScreenContext, opcode: str) -> ScreenResult:
        parsed = parse_opcode(opcode)
        frame = ctx.binding.frame or await self.open(ctx)
        if isinstance(parsed, OpcodeRejection) or parsed.screen is not WidgetScreenId.MENU:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        if parsed.name == "train":
            return await self._train(ctx, frame)
        if parsed.name == "nweek":
            return await start_next_week(ctx, frame)
        target = _HANDOFF.get(parsed.name)
        if target is None:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        return ScreenResult(frame=frame, answer=frame.chat_data, handoff=target)

    async def _train(self, ctx: ScreenContext, frame: WidgetFrame) -> ScreenResult:
        data = read_state(frame.chat_data)
        mode = str(data.get("mode") or "go")
        if mode == "live":
            return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.CONSOLE)
        if mode == "again":
            return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.HOME)
        if mode == "none":
            return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.HOME)

        weekday = data.get("altDay") if mode == "rest" else None
        if mode == "rest" and not isinstance(weekday, int):
            weekday = await self._probe_rest_day(ctx)

        if mode == "rest" and not isinstance(weekday, int):
            return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.HOME)

        try:
            result = await ctx.mediator.send(
                StartTodayWorkoutCommand(
                    telegram_user_id=ctx.user_id,
                    weekday=weekday if isinstance(weekday, int) else None,
                ),
            )
        except DomainError:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        outcome = str(getattr(result, "outcome", "") or "")
        if outcome in {"started", "resumed"}:
            return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.CONSOLE)
        if outcome == "rest":
            found = resolve_alternative(result)
            if found is not None:
                try:
                    started = await ctx.mediator.send(
                        StartTodayWorkoutCommand(telegram_user_id=ctx.user_id, weekday=found[0]),
                    )
                except DomainError:
                    return ScreenResult(frame=frame, answer=PHASE_ERROR)
                if str(getattr(started, "outcome", "") or "") in {"started", "resumed"}:
                    return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.CONSOLE)
        return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.HOME)

    async def _probe_rest_day(self, ctx: ScreenContext) -> int | None:
        today = await ctx.mediator.send(GetTodayWorkoutQuery(telegram_user_id=ctx.user_id))
        found = resolve_alternative(today)
        return found[0] if found else None

    def _frame(self, data: dict[str, object]) -> WidgetFrame:
        return WidgetFrame(
            screen=WidgetScreenId.MENU,
            chat_data=pack_state(data),
            caption="",
            shell_id="menu",
            height=menu_height(data),
        )


def with_hint(frame: WidgetFrame, hint: str) -> WidgetFrame:
    data = read_state(frame.chat_data)
    text = hint.strip()
    if text:
        data["hint"] = text[:80]
    else:
        data.pop("hint", None)
    return WidgetFrame(
        screen=frame.screen,
        chat_data=pack_state(data),
        caption=frame.caption,
        shell_id=frame.shell_id,
        height=menu_height(data) if frame.screen is WidgetScreenId.MENU else frame.height,
    )


def _payload(home: object, today: object) -> dict[str, object]:
    mode = _mode(today)
    weekday = getattr(today, "weekday", None)
    when = WEEKDAY_LABELS.get(weekday, "") if isinstance(weekday, int) else ""
    linked = getattr(home, "linked_coach_user_id", None) is not None
    coach_name = str(getattr(home, "linked_coach_display_name", "") or "").strip()
    data: dict[str, object] = {
        "title": "Главное",
        "when": when,
        "mode": mode,
        "coach": "mine" if linked else "find",
        "cab": "cab" if getattr(home, "show_coach_badge", False) else "apply",
    }
    if linked and coach_name:
        data["coachName"] = coach_name[:36]
    goal = _goal_line(home)
    if goal:
        data["goal"] = goal
    workout = _workout_title(today)
    if workout:
        data["workout"] = workout[:42]
    put_alternative(data, today, again=mode == "again")
    if getattr(today, "week_finished", False):
        data["weekDone"] = 1
    if data["cab"] == "cab":
        data["n"] = int(getattr(home, "active_clients_count", 0) or 0)
    if getattr(home, "is_moderator", False):
        data["mod"] = 1
    return data


def _mode(today: object) -> str:
    screen = str(getattr(today, "screen", "") or "")
    if screen == "session":
        return "live"
    if screen == "no_program":
        return "none"
    if screen == "rest":
        return "rest"
    if getattr(today, "completed_today", False):
        return "again"
    return "go"


def _workout_title(today: object) -> str:
    document = getattr(today, "document", None)
    days = getattr(document, "days", None) if document is not None else None
    if days:
        return str(getattr(days[0], "title", "") or "")
    return ""


def _goal_line(home: object) -> str:
    label = goal_label(getattr(home, "goal", None))
    if label:
        return f"Цель · {label}"[:48]
    if getattr(home, "coach_status", None) == "pending":
        return "Заявка на проверке"
    return ""
