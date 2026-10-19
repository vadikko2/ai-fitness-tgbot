"""Read-only view of a planned training day: one HTML message per exercise."""

from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions

from fitness_bot.domain.program_catalog import training_style_label
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay
from fitness_bot.presentation.keyboards import INTENSITY_LABELS, WEEKDAY_LABELS, program_day_keyboard
from fitness_bot.service.models.queries.match_exercises import GetExerciseGuideResult

EXERCISE_PACK_PAUSE_SECONDS = 0.3

_LINK_PREVIEW_OFF = LinkPreviewOptions(is_disabled=True)
_PLATFORM_LABELS = {"youtube": "YouTube", "rutube": "Rutube"}
_PARAGRAPHS = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ«\"(])")


class AnswerableMessage(Protocol):
    def answer(self, text: str, **kwargs: object) -> Awaitable[object]: ...


def format_planned_exercise_message(
    slot: ExerciseSlot,
    *,
    name: str,
    technique: str = "",
    primary_muscles: Sequence[str] = (),
    secondary_muscles: Sequence[str] = (),
    videos: Sequence[tuple[str, str, str]] = (),
) -> str:
    """Catalog text that exists, plus the slot's sets / reps / weight.

    Bold name, then emoji sections for muscles, the plan, technique, and videos.
    One newline between sections, plan rows, technique paragraphs, and video
    links. A section is left out when it has nothing to show.
    """
    blocks = [f"<b>{html.escape(name.strip() or 'Упражнение')}</b>"]
    muscles = _muscle_section(primary_muscles, secondary_muscles)
    if muscles:
        blocks.append(muscles)
    plan = _plan_section(slot)
    if plan:
        blocks.append(plan)
    technique_text = _technique_blocks(technique)
    if technique_text:
        blocks.append(technique_text)
    links = _video_section(videos)
    if links:
        blocks.append(links)
    return "\n".join(blocks)


def format_day_warmup_message(warmup: str) -> str | None:
    text = warmup.strip()
    if not text:
        return None
    return "<b>Разминка</b>\n" + html.escape(text)


def format_day_cooldown_message(cooldown: str) -> str | None:
    text = cooldown.strip()
    if not text:
        return None
    return "<b>Заминка</b>\n" + html.escape(text)


def format_planned_day_intro(day: WorkoutDay) -> str:
    title = html.escape(day.title.strip() or "Тренировка")
    head = f"<b>{title}</b>"
    weekday = WEEKDAY_LABELS.get(day.weekday) if day.weekday is not None else None
    if weekday:
        head += f" · {html.escape(weekday)}"
    intensity = INTENSITY_LABELS.get(day.intensity.value, day.intensity.value)
    style = training_style_label(day.training_style)
    lines = [head, "", f"{html.escape(intensity.capitalize())} тренировка · {html.escape(style)}."]
    warmup = format_day_warmup_message(day.warmup)
    if warmup:
        lines.extend(["", warmup])
    return "\n".join(lines)


def format_planned_day_outro(day: WorkoutDay) -> str:
    cooldown = format_day_cooldown_message(day.cooldown)
    if cooldown:
        return cooldown
    return "К программе или в меню."


def format_planned_slot_message(
    slot: ExerciseSlot,
    *,
    names: Mapping[UUID, str],
    guides: Mapping[UUID, GetExerciseGuideResult],
    primary_muscles: Mapping[UUID, Sequence[str]] | None = None,
) -> str:
    """Same card as the plan-day pack: catalog text that exists, plus the prescription."""
    return _exercise_message(
        slot,
        names=names,
        guides=guides,
        primary_muscles=primary_muscles or {},
    )


async def send_planned_day_pack(
    message: AnswerableMessage,
    parts: Sequence[str],
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    markups: Sequence[InlineKeyboardMarkup | None] | None = None,
    pause_seconds: float = EXERCISE_PACK_PAUSE_SECONDS,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> None:
    """Send parts in order. Sleep between messages, never before the first.

    ``markups`` is one keyboard per part. Without it, ``reply_markup`` sits on the last message.
    """
    pause = asyncio.sleep if sleep is None else sleep
    last = len(parts) - 1
    for index, text in enumerate(parts):
        if index:
            await pause(pause_seconds)
        if markups is not None:
            markup = markups[index]
        else:
            markup = reply_markup if index == last else None
        await message.answer(
            text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
            link_preview_options=_LINK_PREVIEW_OFF,
        )


async def present_planned_training_day(
    *,
    message: AnswerableMessage,
    day: WorkoutDay,
    day_position: int,
    names: Mapping[UUID, str],
    guides: Mapping[UUID, GetExerciseGuideResult],
    primary_muscles: Mapping[UUID, Sequence[str]] | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> None:
    fallback = primary_muscles or {}
    parts = [format_planned_day_intro(day)]
    for slot in sorted(day.slots, key=lambda item: item.position):
        parts.append(_exercise_message(slot, names=names, guides=guides, primary_muscles=fallback))
    parts.append(format_planned_day_outro(day))
    await send_planned_day_pack(
        message,
        parts,
        reply_markup=program_day_keyboard(day_position=day_position),
        sleep=sleep,
    )


def _exercise_message(
    slot: ExerciseSlot,
    *,
    names: Mapping[UUID, str],
    guides: Mapping[UUID, GetExerciseGuideResult],
    primary_muscles: Mapping[UUID, Sequence[str]],
) -> str:
    guide = guides.get(slot.exercise_id) if slot.exercise_id is not None else None
    found = guide is not None and guide.found
    if found and guide is not None and guide.name.strip():
        name = guide.name
    elif slot.exercise_id is not None and names.get(slot.exercise_id):
        name = names[slot.exercise_id]
    elif slot.custom_request:
        name = slot.custom_request
    else:
        name = "Упражнение"
    technique = guide.technique if found and guide is not None else ""
    primary = list(guide.primary_muscles) if found and guide is not None else []
    secondary = list(guide.secondary_muscles) if found and guide is not None else []
    if not primary and slot.exercise_id is not None:
        primary = [item for item in primary_muscles.get(slot.exercise_id, ()) if item.strip()]
    if not primary and slot.muscle_group:
        primary = [slot.muscle_group]
    videos = [(item.platform, item.url, item.title) for item in guide.videos] if found and guide is not None else []
    return format_planned_exercise_message(
        slot,
        name=name,
        technique=technique,
        primary_muscles=primary,
        secondary_muscles=secondary,
        videos=videos,
    )


def slot_actual_differs_from_plan(slot: ExerciseSlot) -> bool:
    """True when a logged set is not the planned prescription."""
    actual = slot.actual
    if actual is None:
        return False
    return not (
        actual.sets == slot.sets
        and actual.reps == slot.reps
        and actual.duration_seconds == slot.duration_seconds
        and actual.weight_kg == slot.weight_kg
        and not actual.note.strip()
    )


def _section(emoji: str, title: str, body: str) -> str:
    return f"{emoji} <b>{title}</b>\n{body}"


def _muscle_section(primary: Sequence[str], secondary: Sequence[str]) -> str | None:
    muscles = _muscle_names(primary, secondary)
    if not muscles:
        return None
    body = ", ".join(html.escape(item) for item in muscles)
    return _section("💪", "Мышцы", body)


def _plan_section(slot: ExerciseSlot) -> str | None:
    lines: list[str] = []
    reps = _format_reps_line(slot)
    if reps:
        lines.append(reps)
    load = _format_load_line(slot)
    if load:
        lines.append(load)
    if slot.rest_seconds:
        lines.append(f"Отдых: {slot.rest_seconds} с")
    if slot.rpe:
        lines.append(f"Усилие: {slot.rpe}")
    if slot.actual is not None and slot_actual_differs_from_plan(slot):
        lines.append("Факт: " + html.escape(_format_actual_load(slot.actual)))
    if not lines:
        return None
    return _section("📋", "План", "\n".join(lines))


def _format_reps_line(slot: ExerciseSlot) -> str | None:
    if slot.reps is None:
        return None
    if slot.sets:
        return f"Повторы: {slot.sets} × {slot.reps}"
    return f"Повторы: {slot.reps}"


def _format_load_line(slot: ExerciseSlot) -> str | None:
    """Weight for a loaded slot, duration when the slot is timed. Never both."""
    if slot.duration_seconds is not None:
        if slot.sets:
            return f"Время: {slot.sets} × {slot.duration_seconds} с"
        return f"Время: {slot.duration_seconds} с"
    if slot.weight_kg is not None:
        return f"Вес: {html.escape(_format_kg(slot.weight_kg))} кг"
    return None


def _format_actual_load(actual: SlotActual) -> str:
    if actual.reps is not None:
        text = f"{actual.sets}×{actual.reps}"
    else:
        text = f"{actual.sets}×{actual.duration_seconds} с"
    if actual.weight_kg is not None:
        text += f" · {_format_kg(actual.weight_kg)} кг"
    note = actual.note.strip()
    if note:
        text += f" · {note}"
    return text


def _format_kg(weight: Decimal) -> str:
    text = format(weight, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _muscle_names(primary: Sequence[str], secondary: Sequence[str]) -> list[str]:
    seen: list[str] = []
    folded = set()
    for item in (*primary, *secondary):
        text = item.strip()
        key = text.casefold()
        if not text or key in folded:
            continue
        folded.add(key)
        seen.append(text)
    return seen


def _technique_blocks(technique: str) -> str | None:
    raw = technique.strip()
    if not raw:
        return None
    paragraphs = [part.strip() for part in _PARAGRAPHS.split(raw) if part.strip()]
    groups = [_sentences(paragraph) for paragraph in paragraphs]
    split = len(paragraphs) > 1 and bool(re.search(r"[.!?…]", raw))
    split = split or any(len(sentences) > 1 for sentences in groups)
    if not split:
        parts = [part.strip() for part in _PARAGRAPHS.split(raw) if part.strip()]
        body = html.escape("\n".join(parts))
    else:
        chunks: list[str] = []
        for sentences in groups:
            for index in range(0, len(sentences), 2):
                chunk = " ".join(sentences[index : index + 2])
                chunks.append(html.escape(chunk))
        body = "\n".join(chunks)
    return _section("✍️", "Техника", body)


def _sentences(paragraph: str) -> list[str]:
    pieces = [piece.strip() for piece in _SENTENCE_SPLIT.split(paragraph) if piece.strip()]
    return pieces or [paragraph]


def _video_section(videos: Sequence[tuple[str, str, str]]) -> str | None:
    links = _video_links(videos)
    if not links:
        return None
    return _section("▶️", "Видео", links)


def _video_links(videos: Sequence[tuple[str, str, str]]) -> str | None:
    lines: list[str] = []
    for platform, url, title in videos:
        href = url.strip()
        if not href.startswith(("http://", "https://")):
            continue
        platform_label = _PLATFORM_LABELS.get(platform, platform.strip() or "Видео")
        title_text = title.strip()
        href_html = html.escape(href, quote=True)
        if title_text:
            lines.append(f'{html.escape(platform_label)}: <a href="{href_html}">{html.escape(title_text)}</a>')
        else:
            lines.append(f'<a href="{href_html}">{html.escape(platform_label)}</a>')
    if not lines:
        return None
    return "\n".join(lines)
