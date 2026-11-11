"""Session summary: which exercises were done, with sets and reps."""

from __future__ import annotations

import json

from fitness_bot.presentation.widgets.frame import WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.limits import STATE_BYTE_LIMIT
from fitness_bot.presentation.widgets.opcodes import OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.shell import WidgetShell
from fitness_bot.presentation.widgets.state import PHASE_ERROR, as_number, pack_state
from fitness_bot.service.models.queries.match_exercises import GetExerciseNamesQuery
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
        title, rows = await self._rows(ctx)
        return WidgetFrame(
            screen=WidgetScreenId.SUMMARY,
            chat_data=_fit({"title": title, "rows": rows, "n": len(rows)}),
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

    async def _rows(self, ctx: ScreenContext) -> tuple[str, list[str]]:
        history = await ctx.mediator.send(
            GetSessionHistoryQuery(telegram_user_id=ctx.user_id, limit=1),
        )
        items = list(getattr(history, "items", []) or [])
        if items:
            detail = await ctx.mediator.send(
                GetSessionDetailQuery(telegram_user_id=ctx.user_id, session_id=items[0].session_id),
            )
            title = str(getattr(detail, "title", "") or items[0].title or "Тренировка")
            rows = [_line(slot) for slot in list(getattr(detail, "slots", []) or []) if getattr(slot, "actual", None)]
            if rows:
                return title[:40], rows
        return await self._from_today(ctx)

    async def _from_today(self, ctx: ScreenContext) -> tuple[str, list[str]]:
        today = await ctx.mediator.send(GetTodayWorkoutQuery(telegram_user_id=ctx.user_id))
        document = getattr(today, "document", None)
        if document is None:
            return "Тренировка", []
        names = await self._catalog(ctx)
        title = "Тренировка"
        rows: list[str] = []
        for day in document.days:
            title = str(getattr(day, "title", "") or title)
            for slot in day.slots:
                if slot.actual is None:
                    continue
                rows.append(_line_from_slot(slot, names))
        return title[:40], rows

    async def _catalog(self, ctx: ScreenContext) -> dict[str, str]:
        found = await ctx.mediator.send(GetExerciseNamesQuery())
        return dict(getattr(found, "names", {}) or {})


def _line(slot: object) -> str:
    actual = getattr(slot, "actual", None)
    name = str(getattr(slot, "exercise_name", None) or getattr(slot, "custom_request", None) or "Упражнение")
    return _format(name, actual)


def _line_from_slot(slot: object, names: dict[str, str]) -> str:
    exercise_id = getattr(slot, "exercise_id", None)
    name = names.get(str(exercise_id)) if exercise_id is not None else None
    if not name:
        name = getattr(slot, "custom_request", None) or "Упражнение"
    return _format(str(name), getattr(slot, "actual", None))


def _format(name: str, actual: object | None) -> str:
    load = _load(actual)
    short = name.strip()[:36]
    return f"{short} — {load}" if load else short


def _load(actual: object | None) -> str:
    if actual is None:
        return ""
    sets = int(getattr(actual, "sets", 0) or 0)
    reps = getattr(actual, "reps", None)
    duration = getattr(actual, "duration_seconds", None)
    if reps is not None:
        text = f"{sets}×{int(reps)}"
    elif duration is not None:
        text = f"{sets}×{int(duration)} с"
    else:
        text = f"{sets} подх." if sets else ""
    kg = as_number(getattr(actual, "weight_kg", None))
    if kg is not None and text:
        text = f"{text} · {kg} кг"
    return text


def _fit(data: dict[str, object]) -> str:
    rows = [str(item) for item in data.get("rows") or []]
    body = dict(data)
    while True:
        body["rows"] = rows
        body["n"] = len(rows)
        text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        if len(text.encode("utf-8")) <= STATE_BYTE_LIMIT:
            return pack_state(body)
        if not rows:
            body["rows"] = []
            body["n"] = 0
            return pack_state(body)
        if len(rows[-1]) > 24:
            rows[-1] = rows[-1][: max(12, len(rows[-1]) - 8)].rstrip(" —·")
            continue
        rows.pop()
