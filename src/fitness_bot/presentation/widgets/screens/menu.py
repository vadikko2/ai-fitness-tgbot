"""Main hub: train, profile, coach — short and calm."""

from __future__ import annotations

from fitness_bot.presentation.flow_helpers import goal_label
from fitness_bot.presentation.widgets.frame import WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.opcodes import OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.shell import WidgetShell
from fitness_bot.presentation.widgets.state import PHASE_ERROR, pack_state, read_state
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
            data = read_state(frame.chat_data)
            target = WidgetScreenId.CONSOLE if data.get("mode") == "live" else WidgetScreenId.HOME
            return ScreenResult(frame=frame, answer=frame.chat_data, navigate=target)
        target = _HANDOFF.get(parsed.name)
        if target is None:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        return ScreenResult(frame=frame, answer=frame.chat_data, handoff=target)

    def _frame(self, data: dict[str, object]) -> WidgetFrame:
        return WidgetFrame(
            screen=WidgetScreenId.MENU,
            chat_data=pack_state(data),
            caption="",
            shell_id="menu",
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
    )


def _payload(home: object, today: object) -> dict[str, object]:
    mode = _mode(today)
    data: dict[str, object] = {
        "title": "Главное",
        "sub": _subtitle(home),
        "mode": mode,
        "coach": "mine" if getattr(home, "linked_coach_user_id", None) is not None else "find",
        "cab": "cab" if getattr(home, "show_coach_badge", False) else "apply",
    }
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


def _subtitle(home: object) -> str:
    coach = str(getattr(home, "linked_coach_display_name", "") or "").strip()
    if coach:
        return f"Тренер · {coach}"[:48]
    label = goal_label(getattr(home, "goal", None))
    if label:
        return f"Цель · {label}"[:48]
    if getattr(home, "coach_status", None) == "pending":
        return "Заявка на проверке"
    return "Выбери раздел"
