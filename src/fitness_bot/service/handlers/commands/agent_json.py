from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from fitness_bot.domain.enums import ProgramType, TrainingStyle, WorkoutIntensity
from fitness_bot.domain.errors import AgentUnavailable, InvalidWorkoutDocument
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.service.ports.generation_stream import emit_generation_delta
from fitness_bot.service.ports.language_model import LanguageModel
from fitness_bot.service.ports.video_search import CatalogExerciseRecord
from fitness_bot.service.prompts import load_system_prompt, render_prompt

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
_REPLY_MAX = 500


async def _complete_raw(language_model: LanguageModel, *, system: str, user: str) -> str:
    stream = getattr(language_model, "stream", None)
    if callable(stream):
        parts: list[str] = []
        async for chunk in stream(system=system, user=user):
            parts.append(str(chunk))
            await emit_generation_delta("".join(parts))
        return "".join(parts)
    text = await language_model.complete(system=system, user=user)
    await emit_generation_delta(str(text))
    return str(text)


def catalog_json(records: list[CatalogExerciseRecord]) -> str:
    payload = [
        {
            "id": str(record.id),
            "name": record.name,
            "primary_muscles": list(record.primary_muscles),
            "secondary_muscles": list(record.secondary_muscles),
        }
        for record in records
    ]
    return json.dumps(payload, ensure_ascii=False)


def document_json(document: WorkoutDocument) -> str:
    return json.dumps(document.model_dump(mode="json"), ensure_ascii=False)


def workout_document_schema_json() -> str:
    return json.dumps(WorkoutDocument.model_json_schema(), ensure_ascii=False)


def slot_json(slot: ExerciseSlot) -> str:
    return json.dumps(slot.model_dump(mode="json"), ensure_ascii=False)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def extract_json_object(text: str) -> dict[str, Any]:
    text = _strip_fences(text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJECT_RE.search(text)
        if not match:
            raise InvalidWorkoutDocument("model response is not a JSON object") from None
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise InvalidWorkoutDocument("model response must be a JSON object")
    return payload


def _parse_uuid(value: object) -> UUID | None:
    if value is None or value == "" or value == "null":
        return None
    try:
        return UUID(str(value).strip())
    except (ValueError, TypeError, AttributeError):
        # Models often invent truncated ids or put exercise names here.
        return None


def _parse_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _parse_actual(raw: dict[str, Any] | None) -> SlotActual | None:
    if raw is None:
        return None
    return SlotActual(
        sets=int(raw["sets"]),
        reps=int(raw["reps"]) if raw.get("reps") is not None else None,
        duration_seconds=int(raw["duration_seconds"]) if raw.get("duration_seconds") is not None else None,
        weight_kg=_parse_decimal(raw.get("weight_kg")),
        note=str(raw.get("note") or ""),
    )


def _parse_int(value: object, *, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    return int(value)


def _parse_intensity(value: object) -> WorkoutIntensity:
    if value is None or value == "":
        return WorkoutIntensity.MEDIUM
    return WorkoutIntensity(str(value).strip().lower())


def _parse_training_style(value: object) -> TrainingStyle:
    if value is None or value == "":
        return TrainingStyle.CLASSIC
    return TrainingStyle(str(value).strip().lower())


def _assert_training_style_mix(days: list[WorkoutDay]) -> None:
    if len(days) <= 1:
        return
    if all(day.training_style == TrainingStyle.HIT for day in days):
        raise InvalidWorkoutDocument("not all days may use hit training style; mix styles across the week")


def _nonempty_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "null":
        return None
    return text


def _looks_like_id_token(text: str) -> bool:
    """True for UUID fragments / hex junk that must not become a match query."""
    compact = "".join(ch for ch in text if ch.isalnum())
    if len(compact) < 8:
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in compact)


def _parse_slot(raw: dict[str, Any], *, default_position: int = 1) -> ExerciseSlot:
    actual_raw = raw.get("actual")
    actual = _parse_actual(actual_raw) if isinstance(actual_raw, dict) else None
    position = _parse_int(raw.get("position"), default=default_position)
    assert position is not None
    sets = _parse_int(raw.get("sets"), default=3)
    assert sets is not None
    reps = _parse_int(raw.get("reps"))
    duration_seconds = _parse_int(raw.get("duration_seconds"))
    if reps is None and duration_seconds is None:
        reps = 10
    rest_seconds = _parse_int(raw.get("rest_seconds"), default=90)
    assert rest_seconds is not None
    rpe = _parse_int(raw.get("rpe"), default=7)
    assert rpe is not None
    custom = _nonempty_str(raw.get("custom_request"))
    muscle = _nonempty_str(raw.get("muscle_group"))
    raw_exercise_id = raw.get("exercise_id")
    exercise_id = _parse_uuid(raw_exercise_id)
    if exercise_id is None:
        salvage = (
            _nonempty_str(raw_exercise_id) or _nonempty_str(raw.get("name")) or _nonempty_str(raw.get("exercise_name"))
        )
        if salvage is not None and not _looks_like_id_token(salvage):
            custom = custom or salvage
        if custom is None:
            raise InvalidWorkoutDocument(
                f"slot needs a catalog exercise_id UUID or custom_request; got exercise_id={raw_exercise_id!r}",
            )
        muscle = muscle or "общее"
    return ExerciseSlot(
        position=position,
        exercise_id=exercise_id,
        custom_request=custom if exercise_id is None else None,
        muscle_group=muscle if exercise_id is None else None,
        sets=sets,
        reps=reps,
        duration_seconds=duration_seconds,
        weight_kg=_parse_decimal(raw.get("weight_kg")),
        rest_seconds=rest_seconds,
        rpe=rpe,
        technique_note=str(raw.get("technique_note") or ""),
        actual=actual,
    )


def parse_slot(raw: dict[str, Any]) -> ExerciseSlot:
    return _parse_slot(raw)


def parse_workout_document(raw: dict[str, Any], *, default_program_type: ProgramType | None = None) -> WorkoutDocument:
    program_type_raw = raw.get("program_type")
    if program_type_raw is None and default_program_type is not None:
        program_type = default_program_type
    else:
        program_type = ProgramType(str(program_type_raw))
    legacy_style = raw.get("training_style")
    days_raw = raw.get("days")
    if not isinstance(days_raw, list):
        raise InvalidWorkoutDocument("document.days must be a list")
    days: list[WorkoutDay] = []
    for index, day_raw in enumerate(days_raw, start=1):
        if not isinstance(day_raw, dict):
            raise InvalidWorkoutDocument("day must be an object")
        slots_raw = day_raw.get("slots") or []
        if not isinstance(slots_raw, list):
            raise InvalidWorkoutDocument("day.slots must be a list")
        weekday = day_raw.get("weekday")
        title = day_raw.get("title") or day_raw.get("name")
        days.append(
            WorkoutDay(
                weekday=int(weekday) if weekday is not None else None,
                title=str(title or f"день {index}"),
                position=int(day_raw.get("position") or index),
                intensity=_parse_intensity(day_raw.get("intensity")),
                training_style=_parse_training_style(
                    day_raw.get("training_style") if day_raw.get("training_style") is not None else legacy_style,
                ),
                warmup=str(day_raw.get("warmup") or "").strip(),
                cooldown=str(day_raw.get("cooldown") or "").strip(),
                slots=[
                    _parse_slot(slot, default_position=slot_index)
                    for slot_index, slot in enumerate(slots_raw, start=1)
                    if isinstance(slot, dict)
                ],
            ),
        )
    _assert_training_style_mix(days)
    return WorkoutDocument(program_type=program_type, days=days)


def clip_reply(reply: object) -> str:
    text = str(reply or "").strip()
    if len(text) > _REPLY_MAX:
        return text[:_REPLY_MAX]
    return text


def reply_from_payload(payload: dict[str, Any] | None) -> str:
    """Best-effort reply extraction when document/schema validation fails."""
    if not isinstance(payload, dict):
        return ""
    return clip_reply(payload.get("reply"))


def is_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError | ConnectionError | OSError | AgentUnavailable | NotImplementedError):
        return True
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) if response is not None else None
    if isinstance(status, int):
        return status >= 500 or status == 408 or status == 429
    # OpenAI-compatible / httpx transport failures typically expose request or response attrs.
    if response is not None or getattr(exc, "request", None) is not None:
        return True
    return False


async def complete_json(
    language_model: LanguageModel,
    *,
    prompt_name: str,
    prompt_context: dict[str, object],
) -> dict[str, Any]:
    system = load_system_prompt()
    user_prompt = render_prompt(prompt_name, **prompt_context)
    last_error: str | None = None
    for attempt in range(2):
        prompt = user_prompt
        if last_error is not None:
            prompt = f"{user_prompt}\n\nPrevious response failed validation: {last_error}\nReturn corrected JSON only."
        try:
            raw = await _complete_raw(language_model, system=system, user=prompt)
        except Exception as exc:
            if is_transport_error(exc):
                raise AgentUnavailable("language model unavailable") from exc
            raise AgentUnavailable("language model unavailable") from exc
        if not raw or not str(raw).strip():
            raise AgentUnavailable("language model returned empty body")
        try:
            return extract_json_object(str(raw))
        except (InvalidWorkoutDocument, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            last_error = str(exc)
            if attempt == 1:
                raise InvalidWorkoutDocument(last_error) from exc
    raise InvalidWorkoutDocument("schema validation failed")
