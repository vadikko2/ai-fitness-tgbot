"""Session summary: set count, tonnage, and a sparkline of recent working weights."""

from __future__ import annotations

from fitness_bot.presentation.widgets.frame import WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.opcodes import OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.shell import WidgetShell
from fitness_bot.presentation.widgets.state import PHASE_ERROR, as_number, pack_state
from fitness_bot.service.models.queries.session import (
    GetSessionDetailQuery,
    GetSessionHistoryQuery,
    GetTodayWorkoutQuery,
)


class SummaryScreen:
    screen_id = WidgetScreenId.SUMMARY

    def __init__(self, shell: WidgetShell) -> None:
        self.shell = shell

    async def open(self, ctx: ScreenContext) -> WidgetFrame:
        sets, tonnage, spark = await self._stats(ctx)
        data = {"sets": sets, "tonnage": tonnage, "spark": spark}
        return WidgetFrame(
            screen=WidgetScreenId.SUMMARY,
            chat_data=pack_state(data),
            caption="",
            shell_id="summary",
        )

    async def apply(self, ctx: ScreenContext, opcode: str) -> ScreenResult:
        parsed = parse_opcode(opcode)
        frame = ctx.binding.frame or await self.open(ctx)
        if isinstance(parsed, OpcodeRejection) or parsed.screen is not WidgetScreenId.SUMMARY:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        if parsed.name != "home":
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.HOME)

    async def _stats(self, ctx: ScreenContext) -> tuple[int, int, list[int | float]]:
        history = await ctx.mediator.send(
            GetSessionHistoryQuery(telegram_user_id=ctx.user_id, limit=4),
        )
        weights: list[int | float] = []
        sets = 0
        tonnage = 0.0
        first = True
        for item in list(getattr(history, "items", []) or []):
            detail = await ctx.mediator.send(
                GetSessionDetailQuery(telegram_user_id=ctx.user_id, session_id=item.session_id),
            )
            for slot in list(getattr(detail, "slots", []) or []):
                actual = getattr(slot, "actual", None)
                if actual is None:
                    continue
                if first:
                    sets += int(getattr(actual, "sets", 0) or 0)
                    kg = getattr(actual, "weight_kg", None)
                    reps = getattr(actual, "reps", None)
                    if kg is not None and reps:
                        tonnage += float(kg) * int(reps) * int(getattr(actual, "sets", 0) or 0)
                number = as_number(getattr(actual, "weight_kg", None))
                if number is not None:
                    weights.append(number)
            first = False
            if len(weights) >= 12:
                break
        if not weights and sets == 0:
            sets, tonnage, weights = await self._from_today(ctx)
        return sets, int(round(tonnage)), weights[-12:]

    async def _from_today(self, ctx: ScreenContext) -> tuple[int, float, list[int | float]]:
        today = await ctx.mediator.send(GetTodayWorkoutQuery(telegram_user_id=ctx.user_id))
        document = getattr(today, "document", None)
        sets = 0
        tonnage = 0.0
        weights: list[int | float] = []
        if document is None:
            return 0, 0.0, []
        for day in document.days:
            for slot in day.slots:
                actual = slot.actual
                if actual is None:
                    continue
                sets += actual.sets
                if actual.weight_kg is not None and actual.reps:
                    tonnage += float(actual.weight_kg) * actual.reps * actual.sets
                number = as_number(actual.weight_kg)
                if number is not None:
                    weights.append(number)
        return sets, tonnage, weights
