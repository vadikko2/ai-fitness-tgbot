"""Read-only view of a planned training day: one HTML message per exercise."""

from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions

from fitness_bot.domain.program_catalog import training_style_label
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay
from fitness_bot.presentation.keyboards import INTENSITY_LABELS, WEEKDAY_LABELS, program_day_keyboard
from fitness_bot.service.models.queries.match_exercises import GetExerciseGuideResult

EXERCISE_PACK_PAUSE_SECONDS = 0.3

_LINK_PREVIEW_OFF = LinkPreviewOptions(is_disabled=True)
_PLATFORM_LABELS = {"youtube": "YouTube", "rutube": "Rutube"}
_PARAGRAPHS = re.compile(r"\n\s*\n")


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
    """Catalog text that exists, plus the slot's sets / reps / weight."""
    blocks = [f"<b>{html.escape(name.strip() or 'Упражнение')}</b>"]
    muscles = _muscles_line(primary_muscles, secondary_muscles)
    if muscles:
        blocks.append(muscles)
    blocks.append(f"План: <b>{html.escape(_prescription(slot))}</b>")
    technique_text = _technique_block(technique)
    if technique_text:
        blocks.append(technique_text)
    links = _video_links(videos)
    if links:
        blocks.append(links)
    return "\n\n".join(blocks)


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
    reply_markup: InlineKeyboardMarkup,
    pause_seconds: float = EXERCISE_PACK_PAUSE_SECONDS,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> None:
    """Send parts in order. Sleep between messages, never before the first."""
    pause = asyncio.sleep if sleep is None else sleep
    last = len(parts) - 1
    for index, text in enumerate(parts):
        if index:
            await pause(pause_seconds)
        await message.answer(
            text,
            reply_markup=reply_markup if index == last else None,
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


def _prescription(slot: ExerciseSlot) -> str:
    if slot.reps is not None:
        load = f"{slot.sets}×{slot.reps}"
    else:
        load = f"{slot.sets}×{slot.duration_seconds}с"
    if slot.weight_kg is not None:
        load = f"{load} · {_format_kg(slot.weight_kg)} кг"
    extras: list[str] = []
    if slot.rest_seconds:
        extras.append(f"отдых {slot.rest_seconds}с")
    if slot.rpe:
        extras.append(f"RPE {slot.rpe}")
    if extras:
        load = f"{load} · " + " · ".join(extras)
    return load


def _format_kg(weight: Decimal) -> str:
    text = format(weight, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _muscles_line(primary: Sequence[str], secondary: Sequence[str]) -> str | None:
    seen: list[str] = []
    folded = set()
    for item in (*primary, *secondary):
        text = item.strip()
        key = text.casefold()
        if not text or key in folded:
            continue
        folded.add(key)
        seen.append(text)
    if not seen:
        return None
    return "Мышцы: " + ", ".join(html.escape(item) for item in seen)


def _technique_block(technique: str) -> str | None:
    paragraphs = [html.escape(part.strip()) for part in _PARAGRAPHS.split(technique) if part.strip()]
    if not paragraphs:
        return None
    return "\n\n".join(paragraphs)


def _video_links(videos: Sequence[tuple[str, str, str]]) -> str | None:
    lines: list[str] = []
    for platform, url, title in videos:
        href = url.strip()
        if not href.startswith(("http://", "https://")):
            continue
        platform_label = _PLATFORM_LABELS.get(platform, platform.strip() or "Видео")
        title_text = title.strip()
        label = f"{platform_label}: {title_text}" if title_text else platform_label
        lines.append(f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>')
    if not lines:
        return None
    return "\n".join(lines)
