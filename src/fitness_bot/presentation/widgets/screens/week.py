"""One program day in the bubble. Approve uses the existing proposal command."""

from __future__ import annotations

import json
from uuid import UUID

from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDocument
from fitness_bot.presentation.keyboards import WEEKDAY_LABELS
from fitness_bot.presentation.widgets.frame import WidgetFrame, WidgetScreenId, week_height
from fitness_bot.presentation.widgets.opcodes import OpcodeRejection, parse_opcode
from fitness_bot.presentation.widgets.screen import ScreenContext, ScreenResult
from fitness_bot.presentation.widgets.shell import WidgetShell
from fitness_bot.presentation.widgets.state import PHASE_ERROR, as_number, pack_state, read_state
from fitness_bot.service.models.commands.program import ApproveProposalCommand, SelectExerciseForProposalCommand
from fitness_bot.service.models.queries.match_exercises import GetExerciseNamesQuery, MatchExercisesQuery
from fitness_bot.service.models.queries.program import GetPendingProposalQuery

_PAGE = 6
_STATE_LIMIT = 1024


class WeekScreen:
    screen_id = WidgetScreenId.WEEK

    def __init__(self, shell: WidgetShell) -> None:
        self.shell = shell

    async def open(self, ctx: ScreenContext) -> WidgetFrame:
        previous = read_state(ctx.binding.frame.chat_data if ctx.binding.frame else None)
        pending = await ctx.mediator.send(GetPendingProposalQuery(telegram_user_id=ctx.user_id))
        document = getattr(pending, "document", None)
        names = await self._names(ctx)
        return self._frame(
            self._payload(
                document,
                names,
                day=int(previous.get("day") or 0),
                page=int(previous.get("page") or 0),
                sel=int(previous.get("sel") or 0),
                omit={int(item) for item in previous.get("omit") or []},
                alts=list(previous.get("alts") or []),
                ids=list(previous.get("ids") or []),
            ),
        )

    async def apply(self, ctx: ScreenContext, opcode: str) -> ScreenResult:
        parsed = parse_opcode(opcode)
        frame = ctx.binding.frame or await self.open(ctx)
        if isinstance(parsed, OpcodeRejection) or parsed.screen is not WidgetScreenId.WEEK:
            return ScreenResult(frame=frame, answer=PHASE_ERROR)
        data = read_state(frame.chat_data)
        if parsed.name == "day+":
            return await self._turn(ctx, data, 1)
        if parsed.name == "day-":
            return await self._turn(ctx, data, -1)
        if parsed.name == "slot":
            return await self._select(ctx, data, int(parsed.arg or "0"))
        if parsed.name == "drop":
            return await self._drop(ctx, data)
        if parsed.name == "swap" and parsed.arg is None:
            return await self._toggle_swap(ctx, data)
        if parsed.name == "swap" and parsed.arg is not None:
            return await self._swap(ctx, data, int(parsed.arg))
        if parsed.name == "approve":
            return await self._approve(ctx, data)
        return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)

    async def _turn(self, ctx: ScreenContext, data: dict[str, object], step: int) -> ScreenResult:
        pending = await ctx.mediator.send(GetPendingProposalQuery(telegram_user_id=ctx.user_id))
        document = getattr(pending, "document", None)
        count = len(document.days) if document is not None else 1
        day = min(max(0, int(data.get("day") or 0) + step), max(0, count - 1))
        names = await self._names(ctx)
        payload = self._payload(
            document,
            names,
            day=day,
            page=0,
            sel=0,
            omit=set(),
            alts=[],
            ids=[],
        )
        return self._result(payload)

    async def _select(self, ctx: ScreenContext, data: dict[str, object], index: int) -> ScreenResult:
        more = data.get("more")
        slots = list(data.get("slots") or [])
        if more is not None and index == int(more):
            data["page"] = int(data.get("page") or 0) + 1
            data["sel"] = 0
            return await self._rebuild(
                ctx,
                data,
                omit={int(item) for item in data.get("omit") or []},
                alts=[],
                ids=[],
            )
        if index < 0 or index >= len(slots):
            return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)
        data["sel"] = index
        return self._result(data)

    async def _drop(self, ctx: ScreenContext, data: dict[str, object]) -> ScreenResult:
        """Hide the selected slot in this frame.

        The session and proposal keyboards have no command that deletes a slot.
        """
        slots = list(data.get("slots") or [])
        sel = int(data.get("sel") or 0)
        if not slots or sel >= len(slots):
            return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)
        position = int(slots[sel].get("i"))
        omit = {int(item) for item in data.get("omit") or []}
        omit.add(position)
        return await self._rebuild(ctx, data, omit=omit, alts=[], ids=[])

    async def _toggle_swap(self, ctx: ScreenContext, data: dict[str, object]) -> ScreenResult:
        if data.get("alts"):
            data["alts"] = []
            data["ids"] = []
            data.pop("note", None)
            return self._result(data)
        slots = list(data.get("slots") or [])
        sel = int(data.get("sel") or 0)
        if not slots or sel >= len(slots):
            return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)
        name = str(slots[sel].get("name") or "")
        position = int(slots[sel].get("i") or 0)
        current_id, used = await self._swap_exclusions(ctx, data, position=position)
        picks = await self._swap_candidates(ctx, name=name, current_id=current_id, used=used)
        if not picks:
            data["alts"] = []
            data["ids"] = []
            data["note"] = "Не нашёл замену — попробуй другое упражнение"
            return self._result(data)
        data.pop("note", None)
        data["alts"] = [str(item.name)[:36] for item in picks]
        data["ids"] = [str(item.exercise_id) for item in picks]
        return self._result(data)

    async def _swap_exclusions(
        self,
        ctx: ScreenContext,
        data: dict[str, object],
        *,
        position: int,
    ) -> tuple[UUID | None, set[UUID]]:
        pending = await ctx.mediator.send(GetPendingProposalQuery(telegram_user_id=ctx.user_id))
        document = getattr(pending, "document", None)
        days = list(getattr(document, "days", None) or [])
        day_index = int(data.get("day") or 0)
        if day_index < 0 or day_index >= len(days):
            return None, set()
        current = days[day_index]
        used = {slot.exercise_id for slot in current.slots if slot.exercise_id is not None}
        selected = next((slot for slot in current.slots if slot.position == position), None)
        current_id = selected.exercise_id if selected is not None else None
        return current_id, used

    async def _swap_candidates(
        self,
        ctx: ScreenContext,
        *,
        name: str,
        current_id: UUID | None,
        used: set[UUID],
    ) -> list[object]:
        found = await ctx.mediator.send(MatchExercisesQuery(query=name, limit=10))
        picks = [
            item
            for item in list(getattr(found, "items", []) or [])
            if getattr(item, "exercise_id", None) not in used
        ]
        if len(picks) >= 3:
            return picks[:3]
        muscle = None
        if current_id is not None:
            catalog = await ctx.mediator.send(GetExerciseNamesQuery())
            muscles = dict(getattr(catalog, "primary_muscles", {}) or {})
            listed = list(muscles.get(str(current_id), []) or [])
            muscle = str(listed[0]) if listed else None
        if muscle:
            related = await ctx.mediator.send(MatchExercisesQuery(query=muscle, muscle=muscle, limit=10))
            seen = {getattr(item, "exercise_id", None) for item in picks}
            for item in list(getattr(related, "items", []) or []):
                exercise_id = getattr(item, "exercise_id", None)
                if exercise_id is None or exercise_id in used or exercise_id in seen:
                    continue
                picks.append(item)
                seen.add(exercise_id)
                if len(picks) >= 3:
                    break
        return picks[:3]

    async def _swap(self, ctx: ScreenContext, data: dict[str, object], index: int) -> ScreenResult:
        ids = list(data.get("ids") or [])
        slots = list(data.get("slots") or [])
        sel = int(data.get("sel") or 0)
        if index < 0 or index >= len(ids) or sel >= len(slots):
            return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)
        try:
            await ctx.mediator.send(
                SelectExerciseForProposalCommand(
                    telegram_user_id=ctx.user_id,
                    day_position=int(data.get("dp") or 0),
                    slot_position=int(slots[sel].get("i")),
                    exercise_id=UUID(str(ids[index])),
                ),
            )
        except (DomainError, ValueError):
            return ScreenResult(frame=self._frame(data), answer=PHASE_ERROR)
        return await self._rebuild(ctx, data, omit={int(item) for item in data.get("omit") or []}, alts=[], ids=[])

    async def _approve(self, ctx: ScreenContext, data: dict[str, object]) -> ScreenResult:
        result = await ctx.mediator.send(ApproveProposalCommand(telegram_user_id=ctx.user_id))
        blocked = any(
            getattr(result, flag, False) for flag in ("blocked_empty", "blocked_unresolved", "blocked_schedule")
        )
        if blocked:
            noted = dict(data)
            noted["note"] = "Пока нельзя утвердить — проверь дни и упражнения"
            blocked_frame = self._frame(noted)
            return ScreenResult(frame=blocked_frame, answer=blocked_frame.chat_data)
        frame = self._frame(data)
        return ScreenResult(frame=frame, answer=frame.chat_data, navigate=WidgetScreenId.HOME)

    async def _rebuild(
        self,
        ctx: ScreenContext,
        data: dict[str, object],
        *,
        omit: set[int],
        alts: list[str],
        ids: list[str],
    ) -> ScreenResult:
        pending = await ctx.mediator.send(GetPendingProposalQuery(telegram_user_id=ctx.user_id))
        names = await self._names(ctx)
        payload = self._payload(
            getattr(pending, "document", None),
            names,
            day=int(data.get("day") or 0),
            page=int(data.get("page") or 0),
            sel=int(data.get("sel") or 0),
            omit=omit,
            alts=alts,
            ids=ids,
        )
        return self._result(payload)

    def _payload(
        self,
        document: WorkoutDocument | None,
        names: dict[str, str],
        *,
        day: int,
        page: int,
        sel: int,
        omit: set[int],
        alts: list[str],
        ids: list[str],
    ) -> dict[str, object]:
        days = list(document.days) if document is not None else []
        if not days:
            return {
                "day": 0,
                "days": 1,
                "title": "Новая неделя",
                "sel": 0,
                "page": 0,
                "slots": [],
                "more": None,
                "alts": [],
                "ids": [],
                "omit": [],
                "dp": 0,
            }
        day = min(max(0, day), len(days) - 1)
        current = days[day]
        ordered = sorted(current.slots, key=lambda item: item.position)
        visible_slots = [slot for slot in ordered if slot.position not in omit]
        start = page * _PAGE
        if start >= len(visible_slots) and page > 0:
            page = 0
            start = 0
        window = visible_slots[start : start + _PAGE]
        more = start + _PAGE if start + _PAGE < len(visible_slots) else None
        rows = [{"i": slot.position, "name": _slot_name(slot, names), "load": _load(slot)} for slot in window]
        label = WEEKDAY_LABELS.get(current.weekday, "") if current.weekday is not None else ""
        title = f"{label} — {current.title}" if label else current.title
        return {
            "day": day,
            "days": len(days),
            "title": title[:48],
            "sel": min(sel, max(0, len(rows) - 1)),
            "page": page,
            "slots": rows,
            "more": more,
            "alts": alts[:3],
            "ids": ids[:3],
            "omit": sorted(omit),
            "dp": current.position,
        }

    def _frame(self, data: dict[str, object]) -> WidgetFrame:
        return WidgetFrame(
            screen=WidgetScreenId.WEEK,
            chat_data=_fit(data),
            caption="",
            shell_id="week",
            height=week_height(data),
        )

    def _result(self, data: dict[str, object]) -> ScreenResult:
        frame = self._frame(data)
        return ScreenResult(frame=frame, answer=frame.chat_data)

    async def _names(self, ctx: ScreenContext) -> dict[str, str]:
        found = await ctx.mediator.send(GetExerciseNamesQuery())
        return dict(getattr(found, "names", {}) or {})


def _slot_name(slot: ExerciseSlot, names: dict[str, str]) -> str:
    if slot.exercise_id is not None and names.get(str(slot.exercise_id)):
        return str(names[str(slot.exercise_id)])
    return slot.custom_request or "Упражнение"


def _load(slot: ExerciseSlot) -> str:
    parts: list[str] = []
    kg = as_number(slot.weight_kg)
    if kg is not None:
        parts.append(f"{kg}кг")
    if slot.reps is not None:
        parts.append(f"{slot.reps}п")
    elif slot.duration_seconds is not None:
        parts.append(f"{slot.duration_seconds}с")
    return " ".join(parts)[:16]


def _fit(data: dict[str, object]) -> str:
    slots = [dict(item) for item in data.get("slots") or []]
    alts = [str(item) for item in list(data.get("alts") or [])]
    ids = [str(item) for item in list(data.get("ids") or [])]
    limit = 24
    while True:
        body = dict(data)
        body["slots"] = [{**slot, "name": str(slot.get("name") or "")[:limit]} for slot in slots]
        body["alts"] = [item[: max(8, limit)] for item in alts]
        body["ids"] = list(ids)
        text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        size = len(text.encode("utf-8"))
        if size <= _STATE_LIMIT:
            return pack_state(body)
        if limit > 8:
            limit -= 4
            continue
        if alts:
            alts = alts[:-1]
            ids = ids[:-1]
            continue
        body["alts"] = []
        body["ids"] = []
        return pack_state(body)
