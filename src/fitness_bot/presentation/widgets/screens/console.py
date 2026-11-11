"""Workout console: one bubble over the session commands that already exist."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDocument
from fitness_bot.presentation.widgets.frame import WidgetBinding, WidgetFrame, WidgetScreenId
from fitness_bot.presentation.widgets.limits import STATE_BYTE_LIMIT
from fitness_bot.presentation.widgets.opcodes import OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.shell import WidgetShell
from fitness_bot.presentation.widgets.state import PHASE_ERROR, as_number, pack_state, read_state
from fitness_bot.service.models.commands.session import (
    ConfirmExerciseAsPlannedCommand,
    FinalizeSessionCommand,
    RecordSlotActualCommand,
    SwapSessionSlotExerciseCommand,
)
from fitness_bot.service.models.queries.match_exercises import GetExerciseGuideQuery, GetExerciseNamesQuery
from fitness_bot.service.models.queries.session import GetSimilarExercisesQuery, GetTodayWorkoutQuery

_KG_STEP = Decimal("2.5")
_KEEP = frozenset({"rest", "alt", "how", "vid", "kg", "done", "view"})
_ALT_NOTE = {
    "logged": "Уже записано — заменить нельзя.",
    "unresolved": "Это упражнение не из каталога.",
    "no_session": "Замена только во время тренировки.",
}


def _slots(document: WorkoutDocument | None) -> list[ExerciseSlot]:
    if document is None:
        return []
    found: list[ExerciseSlot] = []
    for day in document.days:
        found.extend(sorted(day.slots, key=lambda slot: slot.position))
    return found


def _find(slots: list[ExerciseSlot], position: int) -> ExerciseSlot | None:
    return next((slot for slot in slots if slot.position == position), None)


def _plan(slot: ExerciseSlot) -> str:
    parts = [_slot_load(slot)]
    parts.append(f"{slot.rest_seconds} с")
    return " · ".join(part for part in parts if part)


def _slot_load(slot: ExerciseSlot) -> str:
    actual = slot.actual
    sets = actual.sets if actual is not None else slot.sets
    if actual is not None and actual.reps is not None:
        text = f"{sets}×{actual.reps}"
        kg = as_number(actual.weight_kg)
    elif actual is not None and actual.duration_seconds is not None:
        text = f"{sets}×{actual.duration_seconds} с"
        kg = as_number(actual.weight_kg)
    elif slot.reps is not None:
        text = f"{sets}×{slot.reps}"
        kg = as_number(slot.weight_kg)
    else:
        text = f"{sets}×{slot.duration_seconds} с"
        kg = as_number(slot.weight_kg)
    if kg is not None:
        return f"{text} · {kg} кг"
    return text


def _fit_rows(data: dict[str, object], rows: list[str]) -> None:
    kept = list(rows)
    data["rows"] = kept
    while True:
        data["rows"] = kept
        if _state_bytes(data) <= STATE_BYTE_LIMIT:
            return
        if not kept:
            data["rows"] = []
            return
        if len(kept[-1]) > 20:
            kept[-1] = kept[-1][: max(10, len(kept[-1]) - 8)].rstrip(" —·:")
            continue
        kept.pop()


def _state_bytes(data: dict[str, object]) -> int:
    return len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode())


def _fit_tip(data: dict[str, object], tip: str) -> None:
    text = tip.strip()
    data["tip"] = text
    if _state_bytes(data) <= STATE_BYTE_LIMIT:
        return
    if data.get("timed") in (0, None):
        data.pop("timed", None)
    if not int(data.get("log") or 0):
        data.pop("log", None)
    if _state_bytes(data) <= STATE_BYTE_LIMIT:
        return
    lo = 0
    hi = len(text)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        data["tip"] = text[:mid]
        if _state_bytes(data) <= STATE_BYTE_LIMIT:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    data["tip"] = _tip_ending(text, best)
    while data["tip"] and _state_bytes(data) > STATE_BYTE_LIMIT:
        data["tip"] = str(data["tip"])[:-1].rstrip()


def _tip_ending(text: str, limit: int) -> str:
    if limit >= len(text):
        return text
    chunk = text[:limit].rstrip()
    sentence = max(chunk.rfind("."), chunk.rfind("!"), chunk.rfind("?"))
    if sentence >= 40:
        return chunk[: sentence + 1]
    space = chunk.rfind(" ")
    if space >= 40:
        return chunk[:space].rstrip(" ,;:—-")
    return chunk


def _label(slot: ExerciseSlot, names: dict[str, str]) -> str:
    if slot.exercise_id is not None:
        found = names.get(str(slot.exercise_id))
        if found:
            return str(found)[:48]
    if slot.custom_request:
        return slot.custom_request[:48]
    return "Упражнение"


def _video_rows(guide: object) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in list(getattr(guide, "videos", []) or [])[:3]:
        url = str(getattr(item, "url", "") or "")
        if not url.startswith("https://") or len(url) > 200:
            continue
        title = str(getattr(item, "title", "") or getattr(item, "platform", "") or "Видео")
        rows.append({"t": title[:28], "u": url})
    return rows


def _matches(data: dict[str, object], slot: ExerciseSlot) -> bool:
    if slot.duration_seconds is not None:
        load_ok = int(data.get("reps") or 0) == slot.duration_seconds
    else:
        load_ok = int(data.get("reps") or 0) == (slot.reps or 0)
    return load_ok and data.get("kg") == as_number(slot.weight_kg)


class ConsoleScreen:
    screen_id = WidgetScreenId.CONSOLE

    def __init__(self, shell: WidgetShell) -> None:
        self.shell = shell

    async def open(self, ctx: ScreenContext) -> WidgetFrame:
        previous = _read(ctx.binding)
        if previous.get("ph") == "rpe" and ctx.binding.frame is not None:
            self._start_rest(previous, None)
            return self._frame(previous)
        if previous.get("ph") in _KEEP and ctx.binding.frame is not None:
            return ctx.binding.frame
        today = await ctx.mediator.send(GetTodayWorkoutQuery(telegram_user_id=ctx.user_id))
        names = await self._catalog(ctx)
        slots = _slots(getattr(today, "document", None))
        if previous.get("ph") == "work" and previous.get("pos") is not None:
            slot = _find(slots, int(previous["pos"]))
            if slot is not None:
                data = self._from_slot(slot, slots, names, previous)
                data["kg"] = previous.get("kg", data["kg"])
                data["reps"] = previous.get("reps", data["reps"])
                data["set"] = previous.get("set", 1)
                data["log"] = previous.get("log", 0)
                data["ph"] = "work"
                return self._frame(data)
        return self._frame(self._fresh(slots, names))

    async def apply(self, ctx: ScreenContext, opcode: str) -> ScreenResult:
        parsed = parse_opcode(opcode)
        if isinstance(parsed, OpcodeRejection) or parsed.screen is not WidgetScreenId.CONSOLE:
            frame = await self._ensure(ctx)
            return _error(frame)
        if ctx.binding.frame is None:
            ctx = await self._with_frame(ctx)
        data = _read(ctx.binding)
        phase = str(data.get("ph") or "work")
        if parsed.name == "sync":
            return await self._sync(ctx, data)
        if parsed.name == "ok":
            if phase == "kg":
                return self._commit_kg(data)
            return await self._ok(ctx, data, phase)
        if parsed.name in {"w+", "w-"}:
            return self._step_kg(data, phase, 1 if parsed.name == "w+" else -1)
        if parsed.name in {"r+", "r-"}:
            return self._step_reps(data, phase, 1 if parsed.name == "r+" else -1)
        if parsed.name == "skip":
            return await self._skip(ctx, data, phase)
        if parsed.name == "rpe":
            return await self._rpe(ctx, data, phase, parsed.arg or "")
        if parsed.name == "alt" and parsed.arg is None:
            return await self._show_alts(ctx, data, phase)
        if parsed.name == "alt" and parsed.arg is not None:
            return await self._pick_alt(ctx, data, phase, int(parsed.arg))
        if parsed.name == "back":
            return self._back(data, phase)
        if parsed.name == "how":
            return await self._how(ctx, data, phase)
        if parsed.name == "vid":
            return await self._vid(ctx, data, phase)
        if parsed.name == "kg":
            return self._exact(data, phase)
        if parsed.name == "n":
            return self._type_kg(data, phase, parsed.arg or "")
        if parsed.name == "sum":
            return await self._sum(ctx, data, phase)
        if parsed.name == "view":
            return await self._view(ctx, data, phase)
        if parsed.name == "end":
            return await self._end(ctx, data)
        return _error(self._frame(data))

    async def _sync(self, ctx: ScreenContext, data: dict[str, object]) -> ScreenResult:
        if data.get("ph") != "rest" or time.time() < int(data.get("restUntil") or 0):
            return self._result(data)
        return await self._after_rest(ctx, data)

    async def _ok(self, ctx: ScreenContext, data: dict[str, object], phase: str) -> ScreenResult:
        if phase == "rpe":
            self._start_rest(data, None)
            return self._result(data)
        if phase != "work":
            return self._result(data)
        slot = await self._slot(ctx, data)
        if slot is None:
            return _error(self._frame(data))
        try:
            if _matches(data, slot):
                await ctx.mediator.send(
                    ConfirmExerciseAsPlannedCommand(
                        telegram_user_id=ctx.user_id,
                        slot_position=slot.position,
                    ),
                )
            else:
                await ctx.mediator.send(self._record(ctx, data, slot, note=""))
        except DomainError:
            return _error(self._frame(data))
        data["log"] = int(data.get("log") or 0) + 1
        self._start_rest(data, slot)
        return self._result(data)

    def _step_kg(self, data: dict[str, object], phase: str, sign: int) -> ScreenResult:
        if phase != "work":
            return self._result(data) if phase == "rest" else _error(self._frame(data))
        current = Decimal("0") if data.get("kg") in (None, "") else Decimal(str(data.get("kg")))
        updated = current + (_KG_STEP if sign > 0 else -_KG_STEP)
        data["kg"] = None if updated <= 0 else as_number(updated)
        return self._result(data)

    def _step_reps(self, data: dict[str, object], phase: str, sign: int) -> ScreenResult:
        if phase != "work":
            return _error(self._frame(data))
        data["reps"] = max(1, int(data.get("reps") or 0) + sign)
        return self._result(data)

    async def _skip(self, ctx: ScreenContext, data: dict[str, object], phase: str) -> ScreenResult:
        if phase == "rest":
            return await self._after_rest(ctx, data)
        if phase != "work":
            return _error(self._frame(data))
        return await self._next_exercise(ctx, data)

    async def _rpe(self, ctx: ScreenContext, data: dict[str, object], phase: str, score: str) -> ScreenResult:
        if phase != "rpe":
            return _error(self._frame(data))
        slot = await self._slot(ctx, data)
        if slot is None:
            return _error(self._frame(data))
        try:
            await ctx.mediator.send(self._record(ctx, data, slot, note=f"RPE {score}"))
        except DomainError:
            return _error(self._frame(data))
        self._start_rest(data, slot)
        return self._result(data)

    async def _show_alts(self, ctx: ScreenContext, data: dict[str, object], phase: str) -> ScreenResult:
        if phase != "work" or data.get("pos") is None:
            return _error(self._frame(data))
        found = await ctx.mediator.send(
            GetSimilarExercisesQuery(
                telegram_user_id=ctx.user_id,
                slot_position=int(data["pos"]),
                limit=3,
            ),
        )
        reason = getattr(found, "blocked_reason", None)
        items = [] if reason else list(getattr(found, "items", []) or [])[:3]
        data["ph"] = "alt"
        data["alts"] = [str(item.name)[:40] for item in items]
        data["ids"] = [str(item.exercise_id) for item in items]
        if reason:
            data["note"] = _ALT_NOTE.get(str(reason), "Заменить сейчас нельзя.")
        elif not items:
            data["note"] = "Похожих упражнений нет."
        else:
            data.pop("note", None)
        return self._result(data)

    async def _pick_alt(self, ctx: ScreenContext, data: dict[str, object], phase: str, index: int) -> ScreenResult:
        if phase != "alt":
            return _error(self._frame(data))
        ids = list(data.get("ids") or [])
        if index < 0 or index >= len(ids):
            return _error(self._frame(data))
        try:
            await ctx.mediator.send(
                SwapSessionSlotExerciseCommand(
                    telegram_user_id=ctx.user_id,
                    slot_position=int(data["pos"]),
                    exercise_id=UUID(str(ids[index])),
                ),
            )
        except (DomainError, ValueError):
            return _error(self._frame(data))
        data["ph"] = "work"
        data.pop("alts", None)
        data.pop("ids", None)
        data.pop("note", None)
        return await self._refresh_work(ctx, data)

    async def _refresh_work(self, ctx: ScreenContext, data: dict[str, object]) -> ScreenResult:
        today = await ctx.mediator.send(GetTodayWorkoutQuery(telegram_user_id=ctx.user_id))
        names = await self._catalog(ctx)
        slots = _slots(getattr(today, "document", None))
        slot = _find(slots, int(data["pos"])) if data.get("pos") is not None else None
        if slot is None:
            return self._result(data)
        rebuilt = self._from_slot(slot, slots, names, data)
        rebuilt["set"] = data.get("set", 1)
        rebuilt["log"] = data.get("log", 0)
        rebuilt["ph"] = "work"
        rebuilt["kg"] = data.get("kg", rebuilt["kg"])
        rebuilt["reps"] = data.get("reps", rebuilt["reps"])
        return self._result(rebuilt)

    def _back(self, data: dict[str, object], phase: str) -> ScreenResult:
        if phase not in {"alt", "how", "vid", "kg", "view"}:
            return _error(self._frame(data))
        data["ph"] = "work"
        data.pop("alts", None)
        data.pop("ids", None)
        data.pop("note", None)
        data.pop("tip", None)
        data.pop("vids", None)
        data.pop("draft", None)
        data.pop("rows", None)
        data.pop("pct", None)
        data.pop("title", None)
        return self._result(data)

    async def _view(self, ctx: ScreenContext, data: dict[str, object], phase: str) -> ScreenResult:
        if phase in {"alt", "how", "vid", "kg"}:
            return _error(self._frame(data))
        today = await ctx.mediator.send(GetTodayWorkoutQuery(telegram_user_id=ctx.user_id))
        names = await self._catalog(ctx)
        document = getattr(today, "document", None)
        slots = _slots(document)
        current = int(data.get("pos") or 0)
        rows: list[str] = []
        done = 0
        title = "Тренировка"
        if document is not None and document.days:
            title = str(document.days[0].title or title)
        for slot in slots:
            if slot.actual is not None:
                mark = "d"
                done += 1
            elif slot.position == current:
                mark = "n"
            else:
                mark = "t"
            name = _label(slot, names)
            load = _slot_load(slot)
            rows.append(f"{mark}:{name} — {load}" if load else f"{mark}:{name}")
        pct = int(round(100 * done / len(slots))) if slots else 0
        data["ph"] = "view"
        data["title"] = title[:40]
        data["pct"] = pct
        data.pop("tip", None)
        data.pop("vids", None)
        data.pop("alts", None)
        data.pop("ids", None)
        data.pop("note", None)
        data.pop("draft", None)
        _fit_rows(data, rows)
        return self._result(data)

    async def _end(self, ctx: ScreenContext, data: dict[str, object]) -> ScreenResult:
        try:
            await ctx.mediator.send(FinalizeSessionCommand(telegram_user_id=ctx.user_id))
        except DomainError:
            pass
        data["ph"] = "done"
        data.pop("restUntil", None)
        data.pop("rows", None)
        data.pop("pct", None)
        data.pop("title", None)
        frame = self._frame(data)
        return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.SUMMARY)

    async def _how(self, ctx: ScreenContext, data: dict[str, object], phase: str) -> ScreenResult:
        if phase != "work":
            return _error(self._frame(data))
        slot = await self._slot(ctx, data)
        tip = ""
        if slot is not None and slot.exercise_id is not None:
            guide = await ctx.mediator.send(GetExerciseGuideQuery(exercise_id=slot.exercise_id))
            tip = str(getattr(guide, "technique", "") or "")
        if not tip and slot is not None:
            tip = slot.technique_note
        data["ph"] = "how"
        data.pop("vids", None)
        _fit_tip(data, tip)
        return self._result(data)

    async def _vid(self, ctx: ScreenContext, data: dict[str, object], phase: str) -> ScreenResult:
        if phase != "work":
            return _error(self._frame(data))
        slot = await self._slot(ctx, data)
        rows: list[dict[str, str]] = []
        if slot is not None and slot.exercise_id is not None:
            guide = await ctx.mediator.send(GetExerciseGuideQuery(exercise_id=slot.exercise_id))
            rows = _video_rows(guide)
        data["ph"] = "vid"
        data["vids"] = rows
        data.pop("tip", None)
        return self._result(data)

    def _exact(self, data: dict[str, object], phase: str) -> ScreenResult:
        if phase != "work":
            return _error(self._frame(data))
        current = data.get("kg")
        data["ph"] = "kg"
        data["draft"] = "" if current in (None, "") else str(current)
        return self._result(data)

    def _type_kg(self, data: dict[str, object], phase: str, key: str) -> ScreenResult:
        if phase != "kg" or len(key) != 1:
            return _error(self._frame(data))
        draft = str(data.get("draft") or "")
        if key == "x":
            draft = draft[:-1]
        elif key == ".":
            if "." not in draft:
                draft = f"{draft}."
        elif len(draft.replace(".", "")) < 4:
            draft = f"{draft}{key}"
        data["draft"] = draft[:7]
        return self._result(data)

    def _commit_kg(self, data: dict[str, object]) -> ScreenResult:
        raw = str(data.get("draft") or "").strip().rstrip(".")
        if not raw:
            return _error(self._frame(data))
        try:
            value = Decimal(raw)
        except InvalidOperation:
            return _error(self._frame(data))
        if value < 0 or value > 500:
            return _error(self._frame(data))
        data["kg"] = None if value == 0 else as_number(value)
        data["ph"] = "work"
        data.pop("draft", None)
        return self._result(data)

    async def _sum(self, ctx: ScreenContext, data: dict[str, object], phase: str) -> ScreenResult:
        if phase != "done":
            return _error(self._frame(data))
        return await self._end(ctx, data)

    async def _after_rest(self, ctx: ScreenContext, data: dict[str, object]) -> ScreenResult:
        data.pop("restUntil", None)
        if int(data.get("set") or 1) < int(data.get("sets") or 1):
            data["set"] = int(data.get("set") or 1) + 1
            data["ph"] = "work"
            return self._result(data)
        return await self._next_exercise(ctx, data)

    async def _next_exercise(self, ctx: ScreenContext, data: dict[str, object]) -> ScreenResult:
        today = await ctx.mediator.send(GetTodayWorkoutQuery(telegram_user_id=ctx.user_id))
        names = await self._catalog(ctx)
        slots = _slots(getattr(today, "document", None))
        index = int(data.get("i") or 1)
        if index >= len(slots):
            data["ph"] = "done"
            data.pop("restUntil", None)
            return self._result(data)
        built = self._from_slot(slots[index], slots, names, data)
        built["ph"] = "work"
        built["set"] = 1
        built["log"] = data.get("log", 0)
        return self._result(built)

    async def _catalog(self, ctx: ScreenContext) -> dict[str, str]:
        found = await ctx.mediator.send(GetExerciseNamesQuery())
        return dict(getattr(found, "names", {}) or {})

    async def _slot(self, ctx: ScreenContext, data: dict[str, object]) -> ExerciseSlot | None:
        if data.get("pos") is None:
            return None
        today = await ctx.mediator.send(GetTodayWorkoutQuery(telegram_user_id=ctx.user_id))
        return _find(_slots(getattr(today, "document", None)), int(data["pos"]))

    def _record(
        self,
        ctx: ScreenContext,
        data: dict[str, object],
        slot: ExerciseSlot,
        *,
        note: str,
    ) -> RecordSlotActualCommand:
        timed = bool(data.get("timed"))
        kg = data.get("kg")
        return RecordSlotActualCommand(
            telegram_user_id=ctx.user_id,
            slot_position=slot.position,
            sets=max(1, int(data.get("set") or 1)),
            reps=None if timed else int(data.get("reps") or 0),
            duration_seconds=int(data.get("reps") or 0) if timed else None,
            weight_kg=None if kg in (None, 0) else Decimal(str(kg)),
            note=note,
        )

    def _fresh(self, slots: list[ExerciseSlot], names: dict[str, str]) -> dict[str, object]:
        if not slots:
            return {
                "ph": "done",
                "i": 0,
                "n": 0,
                "set": 0,
                "sets": 0,
                "name": "Нет тренировки",
                "plan": "",
                "kg": None,
                "reps": None,
                "log": 0,
            }
        for slot in slots:
            if slot.actual is None:
                data = self._from_slot(slot, slots, names, {})
                data["ph"] = "work"
                data["set"] = 1
                data["log"] = 0
                return data
        data = self._from_slot(slots[-1], slots, names, {})
        data["ph"] = "done"
        return data

    def _from_slot(
        self,
        slot: ExerciseSlot,
        slots: list[ExerciseSlot],
        names: dict[str, str],
        previous: dict[str, object],
    ) -> dict[str, object]:
        index = next((i for i, item in enumerate(slots) if item.position == slot.position), 0)
        name = _label(slot, names)
        timed = slot.duration_seconds is not None
        return {
            "ph": previous.get("ph") or "work",
            "i": index + 1,
            "n": len(slots),
            "set": 1,
            "sets": slot.sets,
            "name": name,
            "plan": _plan(slot),
            "kg": as_number(slot.weight_kg),
            "reps": slot.duration_seconds if timed else slot.reps,
            "pos": slot.position,
            "timed": 1 if timed else 0,
            "rest": slot.rest_seconds,
            "log": int(previous.get("log") or 0),
        }

    def _start_rest(self, data: dict[str, object], slot: ExerciseSlot | None) -> None:
        seconds = slot.rest_seconds if slot is not None else int(data.get("rest") or 0)
        data["ph"] = "rest"
        data["rest"] = seconds
        data["restUntil"] = int(time.time()) + int(seconds)

    def _result(self, data: dict[str, object]) -> ScreenResult:
        frame = self._frame(data)
        return ScreenResult(frame=frame, answer=frame.chat_data)

    def _frame(self, data: dict[str, object]) -> WidgetFrame:
        return WidgetFrame(
            screen=WidgetScreenId.CONSOLE,
            chat_data=pack_state(data),
            caption="",
            shell_id="console",
        )

    async def _ensure(self, ctx: ScreenContext) -> WidgetFrame:
        if ctx.binding.frame is not None:
            return ctx.binding.frame
        return await self.open(ctx)

    async def _with_frame(self, ctx: ScreenContext) -> ScreenContext:
        frame = await self.open(ctx)
        return replace(ctx, binding=replace(ctx.binding, frame=frame))


def _read(binding: WidgetBinding) -> dict[str, object]:
    if binding.frame is None:
        return {}
    return read_state(binding.frame.chat_data)


def _error(frame: WidgetFrame) -> ScreenResult:
    return ScreenResult(frame=frame, answer=PHASE_ERROR)
