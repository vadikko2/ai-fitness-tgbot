from __future__ import annotations

import html
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from uuid import UUID

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, LinkPreviewOptions, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput, ProgramType, ProposalKind, SessionStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.workout.document import (
    ExerciseSlot,
    WorkoutDocument,
    is_matchable_custom_request,
    unresolved_slot_refs,
)
from fitness_bot.presentation.keyboards import (
    INTENSITY_LABELS,
    PROGRAM_TYPE_LABELS,
    WEEKDAY_LABELS,
    back_to_menu_keyboard,
    back_to_slot_keyboard,
    completion_deviation_actions_keyboard,
    completion_prompt_keyboard,
    exercise_guide_keyboard,
    home_keyboard,
    match_session_exercises_keyboard,
    next_session_actions_keyboard,
    performance_actions_keyboard,
    session_done_today_keyboard,
    session_exercise_actions_keyboard,
    session_no_program_keyboard,
    session_pack_closer_keyboard,
    session_repeat_confirm_keyboard,
    session_rest_keyboard,
    session_restart_confirm_keyboard,
    session_template_edit_keyboard,
    session_template_keyboard,
    similar_exercises_keyboard,
    slot_actions_keyboard,
    slot_load_keyboard,
    slot_weight_keyboard,
    with_exercise_confirmation,
    workout_edit_actions_keyboard,
)
from fitness_bot.presentation.message_draft import assistant_parse_failure_text, message_draft_scope
from fitness_bot.presentation.muscle_emoji import build_slot_nav_items
from fitness_bot.presentation.planned_day_pack import (
    format_day_cooldown_message,
    format_day_warmup_message,
    format_planned_slot_message,
    send_planned_day_pack,
    slot_actual_differs_from_plan,
)
from fitness_bot.presentation.routers.program import render_proposal
from fitness_bot.service.models.commands.program import (
    ApproveProposalCommand,
    DiscardProposalCommand,
    GenerateNextWeekCommand,
    SelectExerciseForProposalCommand,
)
from fitness_bot.service.models.commands.session import (
    BeginSessionCompletionCommand,
    ClearSlotActualCommand,
    ConfirmExerciseAsPlannedCommand,
    FinalizeSessionCommand,
    GenerateNextSessionCommand,
    ProposeSessionDeviationCommand,
    ProposeSlotActualCommand,
    ProposeWorkoutChangeCommand,
    RecordSlotActualCommand,
    ReplaceProgramSlotFromSessionCommand,
    RestartOpenSessionCommand,
    StartSessionFromTemplateCommand,
    StartTodayWorkoutCommand,
    SwapSessionSlotExerciseCommand,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.match_exercises import (
    GetExerciseGuideQuery,
    GetExerciseNamesQuery,
    MatchExercisesQuery,
)
from fitness_bot.service.models.queries.program import GetPendingProposalQuery
from fitness_bot.service.models.queries.session import GetSimilarExercisesQuery, GetTodayWorkoutQuery
from fitness_bot.service.models.queries.users import GetWorkflowQuery

WELLBEING_ADAPT_EDIT_UTTERANCE = "Подстрой сегодняшнюю тренировку под моё самочувствие."
_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
_FACT_MARK = "Факт:"


def _chat_message(message: object) -> Message | None:
    """Real chat messages and test doubles. Inaccessible callbacks have no answer()."""
    if getattr(message, "answer", None) is None:
        return None
    return message  # type: ignore[return-value]


def _weekday_label(weekday: int | None) -> str | None:
    if weekday is None:
        return None
    return WEEKDAY_LABELS.get(weekday)


def _intensity_label(intensity: object) -> str:
    value = getattr(intensity, "value", intensity)
    return INTENSITY_LABELS.get(str(value), str(value))


def _slot_view(slot: ExerciseSlot, names: dict[UUID, str] | None = None) -> dict:
    name_map = names or {}
    return {
        "position": slot.position,
        "exercise_id": str(slot.exercise_id) if slot.exercise_id else None,
        "exercise_name": name_map.get(slot.exercise_id) if slot.exercise_id else None,
        "custom_request": slot.custom_request,
        "muscle_group": slot.muscle_group,
        "sets": slot.sets,
        "reps": slot.reps,
        "duration_seconds": slot.duration_seconds,
        "weight_kg": slot.weight_kg,
        "rest_seconds": slot.rest_seconds,
        "rpe": slot.rpe,
        "actual": (
            {
                "sets": slot.actual.sets,
                "reps": slot.actual.reps,
                "duration_seconds": slot.actual.duration_seconds,
                "weight_kg": slot.actual.weight_kg,
                "note": slot.actual.note,
            }
            if slot.actual
            else None
        ),
    }


def _document_view(document: WorkoutDocument, names: dict[UUID, str] | None = None) -> dict:
    name_map = names or {}
    return {
        "program_type": document.program_type.value,
        "days": [
            {
                "weekday": day.weekday,
                "weekday_label": _weekday_label(day.weekday),
                "title": day.title,
                "position": day.position,
                "intensity": day.intensity.value,
                "intensity_label": _intensity_label(day.intensity),
                "warmup": day.warmup,
                "cooldown": day.cooldown,
                "slots": [_slot_view(slot, name_map) for slot in day.slots],
            }
            for day in document.days
        ],
    }


async def _load_exercise_names(mediator: RequestMediator) -> dict[UUID, str]:
    names, _muscles = await _load_catalog_maps(mediator)
    return names


async def _load_catalog_maps(
    mediator: RequestMediator,
) -> tuple[dict[UUID, str], dict[UUID, tuple[str, ...]]]:
    result = await mediator.send(GetExerciseNamesQuery())
    names = {UUID(key): value for key, value in result.names.items()}
    primary_muscles = {UUID(key): tuple(values) for key, values in (result.primary_muscles or {}).items()}
    return names, primary_muscles


async def _render_document_template(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    template_name: str,
    document: WorkoutDocument,
    **extra: object,
) -> str:
    names = await _load_exercise_names(mediator)
    return jinja_env.get_template(template_name).render(
        document=_document_view(document, names),
        **extra,
    )


def _week_status_context(today) -> dict:
    planned = list(today.planned_weekdays or [])
    completed = list(today.completed_weekdays or [])
    return {
        "weekday_label": _weekday_label(today.weekday),
        "planned_count": len(planned),
        "completed_count": len(completed),
        "week_finished": bool(today.week_finished),
        "planned_weekdays": planned,
        "completed_weekdays": completed,
    }


def _slot_button_items(
    document: WorkoutDocument,
    names: dict[UUID, str],
) -> list[tuple[int, str]]:
    open_slots = [slot for day in document.days for slot in day.slots if slot.actual is None]
    return build_slot_nav_items(open_slots, names=names)


_SESSION_PACK_CHEER = frozenset({"Продолжаем 💪", "Поехали! 💪"})
_SESSION_PACK_CLOSER = "Можно закрыть тренировку."


def _session_pack_closer_text(status_line: str | None) -> str:
    if not status_line:
        return _SESSION_PACK_CLOSER
    kept = [part for part in status_line.split("\n\n") if part and part not in _SESSION_PACK_CHEER]
    if not kept:
        return _SESSION_PACK_CLOSER
    return "\n\n".join(kept)


async def _load_session_guides(mediator: RequestMediator, document: WorkoutDocument):
    guides = {}
    for day in document.days:
        for slot in day.slots:
            if slot.exercise_id is None or slot.exercise_id in guides:
                continue
            guide = await mediator.send(GetExerciseGuideQuery(exercise_id=slot.exercise_id))
            if guide.found:
                guides[slot.exercise_id] = guide
    return guides


def _format_kg(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _next_open_slot_position(document: WorkoutDocument, current: int) -> int | None:
    slots = [slot for day in document.days for slot in day.slots]
    after = [slot.position for slot in slots if slot.position > current and slot.actual is None]
    if after:
        return after[0]
    earlier = [slot.position for slot in slots if slot.position < current and slot.actual is None]
    if earlier:
        return earlier[0]
    return None


def _parse_weight_kg(text: str) -> Decimal | None:
    normalized = text.strip().lower().replace(",", ".")
    if normalized in {"0", "-", "нет", "без", "без веса", "bw", "bodyweight"}:
        return None
    try:
        value = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("вес должен быть числом в кг") from exc
    if value < 0:
        raise ValueError("вес не может быть отрицательным")
    if value == 0:
        return None
    return value


def _parse_positive_int(text: str, *, label: str) -> int:
    try:
        value = int(text.strip())
    except ValueError as exc:
        raise ValueError(f"{label} должны быть целым числом") from exc
    if value <= 0:
        raise ValueError(f"{label} должны быть больше 0")
    return value


def _draft_field(weight_kg: Decimal | None, card_message_id: int | None) -> str:
    weight = "" if weight_kg is None else str(weight_kg)
    if card_message_id is None:
        return weight
    return f"{weight}@{card_message_id}"


def _parse_draft_field(raw: str | None) -> tuple[Decimal | None, int | None]:
    if not raw:
        return None, None
    weight_raw, sep, card_raw = raw.partition("@")
    card_id = int(card_raw) if sep and card_raw.isdigit() else None
    weight = Decimal(weight_raw) if weight_raw else None
    return weight, card_id


def _card_message_id(message: object) -> int | None:
    value = getattr(message, "message_id", None)
    if isinstance(value, int):
        return value
    return None


def _message_html(message: object) -> str:
    html_text = getattr(message, "html_text", None)
    plain = getattr(message, "text", None)
    return f"{html_text or ''}{plain or ''}"


def _planned_load_label(slot: ExerciseSlot) -> str:
    if slot.duration_seconds is not None:
        return f"{slot.duration_seconds}с"
    return f"{slot.reps} повт."


async def _find_session_slot(
    mediator: RequestMediator,
    *,
    telegram_user_id: int,
    position: int,
) -> tuple[object, ExerciseSlot] | None:
    today = await mediator.send(GetTodayWorkoutQuery(telegram_user_id=telegram_user_id))
    if today.document is None:
        return None
    slot = next(
        (item for day in today.document.days for item in day.slots if item.position == position),
        None,
    )
    if slot is None:
        return None
    return today, slot


async def _show_slot_screen(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    position: int,
    prefix: str | None = None,
    swapped_from: tuple[str, str] | None = None,
    offer_program_swap: bool = False,
) -> None:
    found = await _find_session_slot(mediator, telegram_user_id=telegram_user_id, position=position)
    if found is None:
        await message.answer("Упражнение не найдено.")
        return
    today, slot = found
    names = await _load_exercise_names(mediator)
    text = jinja_env.get_template("session_slot.j2").render(slot=_slot_view(slot, names))
    if prefix:
        text = f"{prefix}\n\n{text}"
    has_video = position in (today.technique_video_positions or [])
    await message.answer(
        text,
        reply_markup=slot_actions_keyboard(
            position=position,
            has_actual=slot.actual is not None,
            has_technique_video=has_video,
            has_catalog_guide=slot.exercise_id is not None,
            can_swap=(
                slot.actual is None
                and slot.exercise_id is not None
                and today.session_status == SessionStatus.IN_PROGRESS
            ),
            swapped_from=swapped_from,
            offer_program_swap=offer_program_swap,
        ),
    )


_SIMILAR_BLOCKED_TEXT = {
    "no_session": "Замена упражнения доступна только во время тренировки.",
    "unresolved": "Сначала выбери упражнение из каталога.",
    "logged": "По этому упражнению уже записан факт — заменить его нельзя.",
}


def _parse_slot_swap(data: str) -> tuple[int, UUID] | None:
    """slot_swap:<position>:<exercise_id>. Incomplete or legacy payloads return None."""
    parts = data.split(":")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2]:
        return None
    try:
        return int(parts[1]), UUID(parts[2])
    except ValueError:
        return None


async def _edit_in_place(message: object, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    editor = getattr(message, "edit_text", None)
    if editor is None:
        return
    try:
        await editor(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            link_preview_options=_NO_PREVIEW,
        )
    except TelegramBadRequest:
        return


async def _edit_live_exercise_card(message: object, *, mediator: RequestMediator, slot: ExerciseSlot) -> None:
    """Normal exercise card: catalog text and the three live buttons."""
    text = await _render_pack_slot(mediator, slot)
    await _edit_in_place(
        message,
        text,
        session_exercise_actions_keyboard(position=slot.position, confirmed=slot.actual is not None),
    )


async def show_similar_exercises(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: object,
    telegram_user_id: int,
    position: int,
    offset: int = 0,
) -> str | None:
    """Edit this message into the similar-exercise picker. Return alert text when swap is blocked."""
    result = await mediator.send(
        GetSimilarExercisesQuery(
            telegram_user_id=telegram_user_id,
            slot_position=position,
            offset=offset,
            limit=3,
        ),
    )
    if result.blocked_reason is not None:
        return _SIMILAR_BLOCKED_TEXT[result.blocked_reason]
    text = jinja_env.get_template("slot_similar.j2").render(exercise_name=result.exercise_name or "упражнение").strip()
    if result.has_more:
        next_offset: int | None = result.offset + len(result.items)
    else:
        next_offset = 0 if result.offset > 0 else None
    await _edit_in_place(
        message,
        text,
        similar_exercises_keyboard(
            position=position,
            items=[(str(item.exercise_id), item.name) for item in result.items],
            next_offset=next_offset,
        ),
    )
    return None


async def _show_session_card(
    *,
    mediator: RequestMediator,
    message: Message,
    document: WorkoutDocument,
    status_line: str | None = None,
    offer_log: bool = True,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> None:
    """One message per exercise, with that slot's actions, then one closer. Not the old button wall."""
    names, primary_muscles = await _load_catalog_maps(mediator)
    guides = await _load_session_guides(mediator, document)
    parts: list[str] = []
    markups: list[InlineKeyboardMarkup | None] = []
    for day in document.days:
        warmup = format_day_warmup_message(day.warmup)
        if warmup:
            parts.append(warmup)
            markups.append(None)
        for slot in sorted(day.slots, key=lambda item: item.position):
            parts.append(
                format_planned_slot_message(
                    slot,
                    names=names,
                    guides=guides,
                    primary_muscles=primary_muscles,
                ),
            )
            if offer_log:
                markups.append(
                    session_exercise_actions_keyboard(
                        position=slot.position,
                        confirmed=slot.actual is not None,
                    ),
                )
            else:
                markups.append(None)
        cooldown = format_day_cooldown_message(day.cooldown)
        if cooldown:
            parts.append(cooldown)
            markups.append(None)
    parts.append(_session_pack_closer_text(status_line))
    markups.append(session_pack_closer_keyboard() if offer_log else back_to_menu_keyboard())
    await send_planned_day_pack(message, parts, markups=markups, sleep=sleep)


async def _render_pack_slot(mediator: RequestMediator, slot: ExerciseSlot) -> str:
    names, primary_muscles = await _load_catalog_maps(mediator)
    guides = {}
    if slot.exercise_id is not None:
        guide = await mediator.send(GetExerciseGuideQuery(exercise_id=slot.exercise_id))
        if guide.found:
            guides[slot.exercise_id] = guide
    return format_planned_slot_message(
        slot,
        names=names,
        guides=guides,
        primary_muscles=primary_muscles,
    )


async def _edit_exercise_card(
    message: Message,
    *,
    mediator: RequestMediator,
    slot: ExerciseSlot,
    confirmed: bool,
    card_message_id: int | None = None,
) -> None:
    """Flip the confirm button on the exercise card. No new chat bubble."""
    text = None
    same_message = card_message_id is None or card_message_id == _card_message_id(message)
    body = _message_html(message) if same_message else ""
    if slot_actual_differs_from_plan(slot) or _FACT_MARK in body:
        text = await _render_pack_slot(mediator, slot)
    if same_message:
        markup = with_exercise_confirmation(
            getattr(message, "reply_markup", None),
            position=slot.position,
            confirmed=confirmed,
        )
        try:
            if text is not None and getattr(message, "edit_text", None) is not None:
                await message.edit_text(
                    text,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=_NO_PREVIEW,
                )
                return
            editor = getattr(message, "edit_reply_markup", None)
            if editor is not None:
                await editor(reply_markup=markup)
        except TelegramBadRequest:
            return
        return
    if card_message_id is None:
        return
    markup = session_exercise_actions_keyboard(position=slot.position, confirmed=confirmed)
    bot = getattr(message, "bot", None)
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    if bot is None or chat_id is None:
        return
    try:
        if text is not None:
            await bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=card_message_id,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
                link_preview_options=_NO_PREVIEW,
            )
            return
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=card_message_id,
            reply_markup=markup,
        )
    except TelegramBadRequest:
        return


async def _ask_slot_weight(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    position: int,
    card_message_id: int | None = None,
) -> None:
    found = await _find_session_slot(mediator, telegram_user_id=telegram_user_id, position=position)
    if found is None:
        await message.answer("Упражнение не найдено.")
        return
    _, slot = found
    names = await _load_exercise_names(mediator)
    planned_weight = _format_kg(slot.weight_kg)
    await mediator.send(
        ExpectInputCommand(
            telegram_user_id=telegram_user_id,
            expected_input=ExpectedInput.SLOT_WEIGHT,
            expected_field=_draft_field(None, card_message_id),
            focus_slot=position,
        ),
    )
    text = jinja_env.get_template("slot_ask_weight.j2").render(
        position=position,
        exercise_name=names.get(slot.exercise_id) if slot.exercise_id else slot.custom_request,
        planned_weight_kg=planned_weight,
    )
    await message.answer(text, reply_markup=slot_weight_keyboard(position=position, planned_weight_kg=planned_weight))


async def _ask_slot_load(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    position: int,
    weight_kg: Decimal | None,
    card_message_id: int | None = None,
) -> None:
    found = await _find_session_slot(mediator, telegram_user_id=telegram_user_id, position=position)
    if found is None:
        await message.answer("Упражнение не найдено.")
        return
    _, slot = found
    names = await _load_exercise_names(mediator)
    uses_duration = slot.duration_seconds is not None
    planned_label = _planned_load_label(slot)
    await mediator.send(
        ExpectInputCommand(
            telegram_user_id=telegram_user_id,
            expected_input=ExpectedInput.SLOT_LOAD,
            expected_field=_draft_field(weight_kg, card_message_id),
            focus_slot=position,
        ),
    )
    text = jinja_env.get_template("slot_ask_load.j2").render(
        position=position,
        exercise_name=names.get(slot.exercise_id) if slot.exercise_id else slot.custom_request,
        uses_duration=uses_duration,
        planned_label=planned_label,
        weight_kg=_format_kg(weight_kg),
    )
    await message.answer(text, reply_markup=slot_load_keyboard(position=position, planned_label=planned_label))


async def _record_slot_actual(
    *,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    position: int,
    weight_kg: Decimal | None,
    reps: int | None,
    duration_seconds: int | None,
    card_message_id: int | None,
) -> None:
    found = await _find_session_slot(mediator, telegram_user_id=telegram_user_id, position=position)
    if found is None:
        await message.answer("Упражнение не найдено.")
        return
    _, slot = found
    result = await mediator.send(
        RecordSlotActualCommand(
            telegram_user_id=telegram_user_id,
            slot_position=position,
            sets=slot.sets,
            reps=reps,
            duration_seconds=duration_seconds,
            weight_kg=weight_kg,
        ),
    )
    if card_message_id is None:
        return
    await _edit_exercise_card(
        message,
        mediator=mediator,
        slot=result.slot,
        confirmed=True,
        card_message_id=card_message_id,
    )


async def render_workout_edit_proposal(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    reply: str = "",
    document: WorkoutDocument | None = None,
    program_type: ProgramType | None = None,
    telegram_user_id: int | None = None,
) -> None:
    type_value = program_type.value if program_type else (document.program_type.value if document else "")
    text = jinja_env.get_template("proposal.j2").render(
        reply=reply,
        document=_document_view(document) if document else None,
        program_type_label=PROGRAM_TYPE_LABELS.get(type_value, type_value),
        missing_weekdays=False,
    )
    can_approve = False
    if document is not None:
        try:
            document.assert_approvable()
            can_approve = True
        except DomainError:
            can_approve = False
    await message.answer(text, reply_markup=workout_edit_actions_keyboard(can_approve=can_approve))

    if document is None:
        return
    for day_position, slot_position, custom_request, muscle_group in unresolved_slot_refs(document):
        _ = day_position
        if not is_matchable_custom_request(custom_request):
            continue
        matches = await mediator.send(
            MatchExercisesQuery(query=custom_request, muscle=muscle_group, limit=5),
        )
        if not matches.items:
            await message.answer(f"Для «{custom_request}» совпадений в каталоге нет. Переформулируй текстом.")
            continue
        await message.answer(
            f"Выбери упражнение для слота {slot_position}:",
            reply_markup=match_session_exercises_keyboard(
                slot_position=slot_position,
                items=[(str(item.exercise_id), item.name) for item in matches.items],
            ),
        )


async def render_performance_proposal(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    reply: str = "",
    document: WorkoutDocument | None = None,
    slot_position: int | None = None,
    telegram_user_id: int | None = None,
) -> None:
    names = await _load_exercise_names(mediator) if document is not None else {}
    slot_view = None
    if document is not None and slot_position is not None:
        for day in document.days:
            for slot in day.slots:
                if slot.position == slot_position:
                    slot_view = _slot_view(slot, names)
                    break
    text = jinja_env.get_template("proposal.j2").render(
        reply=reply,
        document=_document_view(document, names) if document else None,
        program_type_label="",
        missing_weekdays=False,
    )
    if slot_view is not None:
        text = jinja_env.get_template("session_slot.j2").render(slot=slot_view)
        if reply:
            text = f"{reply}\n\n{text}"
    can_approve = document is not None
    await message.answer(text, reply_markup=performance_actions_keyboard(can_approve=can_approve))


async def render_completion_deviation_proposal(
    *,
    jinja_env: Environment,
    message: Message,
    reply: str = "",
    document: WorkoutDocument | None = None,
    telegram_user_id: int | None = None,
) -> None:
    text = jinja_env.get_template("proposal.j2").render(
        reply=reply,
        document=_document_view(document) if document else None,
        program_type_label="",
        missing_weekdays=False,
    )
    can_approve = False
    if document is not None:
        try:
            document.assert_approvable()
            can_approve = True
        except DomainError:
            can_approve = False
    await message.answer(text, reply_markup=completion_deviation_actions_keyboard(can_approve=can_approve))


async def render_next_session_proposal(
    *,
    jinja_env: Environment,
    message: Message,
    reply: str = "",
    document: WorkoutDocument | None = None,
    telegram_user_id: int | None = None,
    offer_plain_start: bool = False,
) -> None:
    type_value = document.program_type.value if document else ""
    text = jinja_env.get_template("proposal.j2").render(
        reply=reply,
        document=_document_view(document) if document else None,
        program_type_label=PROGRAM_TYPE_LABELS.get(type_value, type_value),
        missing_weekdays=False,
    )
    can_approve = False
    if document is not None:
        try:
            document.assert_approvable()
            can_approve = True
        except DomainError:
            can_approve = False
    await message.answer(
        text,
        reply_markup=next_session_actions_keyboard(can_approve=can_approve, offer_plain_start=offer_plain_start),
    )


async def propose_wellbeing_session(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    bot: object,
    telegram_user_id: int,
    offer_plain_start: bool = False,
    report_failures: bool = True,
) -> bool:
    """Draft today's session against fresh wellbeing notes. Returns False when no draft was shown."""
    draft_preview = ""
    async with message_draft_scope(bot, message.chat.id) as draft:
        result = await mediator.send(
            GenerateNextSessionCommand(telegram_user_id=telegram_user_id, adapt_for_wellbeing=True),
        )
        draft_preview = draft.preview_text
    if result.agent_unavailable or result.schema_failed or result.document is None:
        if report_failures:
            if result.agent_unavailable:
                await message.answer(
                    jinja_env.get_template("agent_unavailable.j2").render(),
                    reply_markup=home_keyboard(),
                )
            else:
                await message.answer(
                    assistant_parse_failure_text(
                        result.reply or draft_preview,
                        hint="Не удалось разобрать ответ помощника. Попробуй ещё раз.",
                    ),
                )
        return False
    await render_next_session_proposal(
        jinja_env=jinja_env,
        message=message,
        reply=result.reply,
        document=result.document,
        telegram_user_id=telegram_user_id,
        offer_plain_start=offer_plain_start,
    )
    return True


async def propose_wellbeing_workout_edit(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    bot: object,
    telegram_user_id: int,
) -> None:
    """Draft an edit of the open session against fresh wellbeing notes."""
    draft_preview = ""
    async with message_draft_scope(bot, message.chat.id) as draft:
        result = await mediator.send(
            ProposeWorkoutChangeCommand(
                telegram_user_id=telegram_user_id,
                utterance=WELLBEING_ADAPT_EDIT_UTTERANCE,
                adapt_for_wellbeing=True,
            ),
        )
        draft_preview = draft.preview_text
    if result.agent_unavailable:
        await message.answer(jinja_env.get_template("agent_unavailable.j2").render(), reply_markup=home_keyboard())
        return
    if result.schema_failed or result.document is None:
        await message.answer(assistant_parse_failure_text(result.reply or draft_preview))
        return
    await render_workout_edit_proposal(
        jinja_env=jinja_env,
        mediator=mediator,
        message=message,
        reply=result.reply,
        document=result.document,
        telegram_user_id=telegram_user_id,
    )


def _alternative(weekday: int | None, title: str | None) -> tuple[int, str] | None:
    if weekday is None or not title:
        return None
    return weekday, title


def _alternative_context(alternative: tuple[int, str] | None) -> dict:
    if alternative is None:
        return {"alternative_title": None, "alternative_label": None}
    return {"alternative_title": alternative[1], "alternative_label": _weekday_label(alternative[0])}


def _wellbeing_banner(note: str | None) -> str:
    quoted = f"Ты отметил: «{html.escape(note[:120])}»" if note else "Есть свежая отметка самочувствия"
    return f"🙂 {quoted}. Тренировка начата по плану."


async def start_workout_one_tap(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    weekday: int | None = None,
) -> None:
    """One tap: resume or start the planned day and send one message per exercise."""
    try:
        result = await mediator.send(StartTodayWorkoutCommand(telegram_user_id=telegram_user_id, weekday=weekday))
    except DomainError as exc:
        await message.answer(f"Не удалось начать: {exc}")
        return
    progress = {
        "planned_count": result.planned_count,
        "completed_count": result.completed_count,
        "week_finished": result.week_finished,
    }
    alternative = _alternative(result.alternative_weekday, result.alternative_title)
    if result.outcome == "no_program":
        text = jinja_env.get_template("session_no_program.j2").render()
        await message.answer(text, reply_markup=session_no_program_keyboard())
        return
    if result.outcome == "rest":
        text = jinja_env.get_template("session_rest.j2").render(
            weekday_label=_weekday_label(result.weekday),
            **progress,
            **_alternative_context(alternative),
        )
        await message.answer(
            text,
            reply_markup=session_rest_keyboard(week_finished=result.week_finished, alternative=alternative),
        )
        return
    if result.outcome == "already_done":
        text = jinja_env.get_template("session_done_today.j2").render(**progress, **_alternative_context(alternative))
        await message.answer(
            text,
            reply_markup=session_done_today_keyboard(weekday=result.weekday, alternative=alternative),
        )
        return
    assert result.document is not None
    in_progress = result.session_status == SessionStatus.IN_PROGRESS
    show_wellbeing = result.has_unapplied_wellbeing and in_progress
    lines = ["Продолжаем 💪" if result.outcome == "resumed" else "Поехали! 💪"]
    if show_wellbeing:
        lines.append(_wellbeing_banner(result.wellbeing_note))
    await _show_session_card(
        mediator=mediator,
        message=message,
        document=result.document,
        status_line="\n\n".join(lines),
    )


def create_session_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="session")

    @router.callback_query(F.data == "sess_go")
    async def handle_sess_go(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await callback.answer()
        if not isinstance(callback.message, Message):
            return
        await start_workout_one_tap(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
        )

    @router.callback_query(F.data.startswith("sess_go_day:"))
    async def handle_sess_go_day(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        await callback.answer()
        raw = callback.data.split(":", 1)[1]
        if not isinstance(callback.message, Message) or not raw.isdigit():
            return
        await start_workout_one_tap(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            weekday=int(raw),
        )

    @router.callback_query(F.data == "sess")
    async def handle_sess(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        today = await mediator.send(GetTodayWorkoutQuery(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        if today.screen == "session" and today.document is not None:
            chat = _chat_message(callback.message)
            if chat is not None:
                await _show_session_card(
                    mediator=mediator,
                    message=chat,
                    document=today.document,
                )
            await callback.answer()
        elif today.screen == "template" and today.document is not None:
            week = _week_status_context(today)
            text = await _render_document_template(
                jinja_env=jinja_env,
                mediator=mediator,
                template_name="session_template.j2",
                document=today.document,
                **week,
            )
            if callback.message:
                await callback.message.answer(
                    text,
                    reply_markup=session_template_keyboard(
                        week_finished=bool(today.week_finished),
                        has_unapplied_wellbeing=bool(today.has_unapplied_wellbeing),
                    ),
                )
            await callback.answer()
        elif today.screen == "rest":
            week = _week_status_context(today)
            alternative = _alternative(today.alternative_weekday, today.alternative_title)
            text = jinja_env.get_template("session_rest.j2").render(**week, **_alternative_context(alternative))
            if callback.message:
                await callback.message.answer(
                    text,
                    reply_markup=session_rest_keyboard(
                        week_finished=bool(today.week_finished),
                        alternative=alternative,
                    ),
                )
            await callback.answer()
        else:
            text = jinja_env.get_template("session_no_program.j2").render()
            if callback.message:
                await callback.message.answer(text, reply_markup=session_no_program_keyboard())
            await callback.answer()

    async def _start_plain_session(callback: CallbackQuery, *, status_line: str | None = None) -> None:
        assert callback.from_user is not None
        try:
            result = await mediator.send(StartSessionFromTemplateCommand(telegram_user_id=callback.from_user.id))
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось начать: {exc}")
            return
        if callback.message is None:
            return
        if result.needs_repeat_confirmation:
            text = jinja_env.get_template("session_repeat_confirm.j2").render()
            await callback.message.answer(text, reply_markup=session_repeat_confirm_keyboard())
            return
        if result.document is None:
            await callback.message.answer("Не удалось начать тренировку.")
            return
        assert isinstance(callback.message, Message)
        await _show_session_card(
            mediator=mediator,
            message=callback.message,
            document=result.document,
            status_line=status_line,
        )

    @router.callback_query(F.data == "sess_plan")
    async def handle_sess_plan(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        today = await mediator.send(GetTodayWorkoutQuery(telegram_user_id=callback.from_user.id))
        done_today = today.weekday is not None and today.weekday in (today.completed_weekdays or [])
        if (
            today.screen == "template"
            and today.has_unapplied_wellbeing
            and not done_today
            and isinstance(callback.message, Message)
        ):
            await callback.answer()
            try:
                shown = await propose_wellbeing_session(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=callback.message,
                    bot=callback.bot,
                    telegram_user_id=callback.from_user.id,
                    offer_plain_start=True,
                    report_failures=False,
                )
            except DomainError:
                shown = False
            if not shown:
                await _start_plain_session(
                    callback,
                    status_line="⚠️ Не получилось учесть самочувствие — начали как в плане.",
                )
            return
        await _start_plain_session(callback)
        await callback.answer()

    @router.callback_query(F.data == "sess_plan_raw")
    async def handle_sess_plan_raw(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        pending = await mediator.send(GetPendingProposalQuery(telegram_user_id=callback.from_user.id))
        if pending.proposal_id is not None and pending.kind == ProposalKind.NEXT_SESSION:
            await mediator.send(DiscardProposalCommand(telegram_user_id=callback.from_user.id))
        await _start_plain_session(callback)
        await callback.answer()

    @router.callback_query(F.data.startswith("sess_plan_repeat"))
    async def handle_sess_plan_repeat(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        _, _, raw_weekday = (callback.data or "").partition(":")
        try:
            result = await mediator.send(
                StartSessionFromTemplateCommand(
                    telegram_user_id=callback.from_user.id,
                    overwrite_completed=True,
                    weekday=int(raw_weekday) if raw_weekday.isdigit() else None,
                ),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось начать: {exc}")
            await callback.answer()
            return
        chat = _chat_message(callback.message)
        if chat is None or result.document is None:
            await callback.answer()
            return
        await _show_session_card(
            mediator=mediator,
            message=chat,
            document=result.document,
        )
        await callback.answer()

    @router.callback_query(F.data == "sess_tmpl_edit")
    async def handle_sess_tmpl_edit(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer()
            return
        text = jinja_env.get_template("session_template_edit.j2").render()
        if callback.message:
            await callback.message.answer(text, reply_markup=session_template_edit_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "sess_tmpl_edit_text")
    async def handle_sess_tmpl_edit_text(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        if callback.message is None:
            await callback.answer()
            return
        try:
            result = await mediator.send(StartSessionFromTemplateCommand(telegram_user_id=callback.from_user.id))
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось начать: {exc}")
            await callback.answer()
            return
        if result.needs_repeat_confirmation:
            text = jinja_env.get_template("session_repeat_confirm.j2").render()
            if callback.message:
                await callback.message.answer(
                    text + "\n\nПосле повтора откроется сегодняшняя тренировка.",
                    reply_markup=session_repeat_confirm_keyboard(),
                )
            await callback.answer()
            return
        chat = _chat_message(callback.message)
        if result.document is None:
            if chat is not None:
                await chat.answer("Не удалось начать тренировку.")
            await callback.answer()
            return
        if chat is None:
            await callback.answer()
            return
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.PROPOSAL_UTTERANCE,
                expected_field="workout_edit",
            ),
        )
        await _show_session_card(
            mediator=mediator,
            message=chat,
            document=result.document,
            status_line="Напиши или продиктуй голосом, что поменять в сегодняшней тренировке.",
            offer_log=False,
        )
        await callback.answer()

    @router.callback_query(F.data == "sess_gen")
    async def handle_sess_gen(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        if callback.message is None:
            await callback.answer()
            return
        await callback.answer()
        draft_preview = ""
        try:
            async with message_draft_scope(callback.bot, callback.message.chat.id) as draft:
                result = await mediator.send(GenerateNextSessionCommand(telegram_user_id=callback.from_user.id))
                draft_preview = draft.preview_text
        except DomainError as exc:
            await callback.message.answer(f"Не удалось сгенерировать: {exc}")
            return
        if result.agent_unavailable:
            await callback.message.answer(
                jinja_env.get_template("agent_unavailable.j2").render(),
                reply_markup=home_keyboard(),
            )
            return
        if result.schema_failed or result.document is None:
            await callback.message.answer(
                assistant_parse_failure_text(
                    result.reply or draft_preview,
                    hint="Не удалось разобрать ответ помощника. Попробуй ещё раз.",
                ),
            )
            return
        await render_next_session_proposal(
            jinja_env=jinja_env,
            message=callback.message,
            reply=result.reply,
            document=result.document,
            telegram_user_id=callback.from_user.id,
        )

    @router.callback_query(F.data == "sess_new_week")
    async def handle_sess_new_week(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        if callback.message is None:
            await callback.answer()
            return
        await callback.answer()
        draft_preview = ""
        try:
            async with message_draft_scope(callback.bot, callback.message.chat.id) as draft:
                result = await mediator.send(GenerateNextWeekCommand(telegram_user_id=callback.from_user.id))
                draft_preview = draft.preview_text
        except DomainError as exc:
            await callback.message.answer(f"Не удалось сгенерировать неделю: {exc}")
            return
        if result.agent_unavailable:
            await callback.message.answer(
                jinja_env.get_template("agent_unavailable.j2").render(),
                reply_markup=home_keyboard(),
            )
            return
        if result.schema_failed or result.document is None:
            await callback.message.answer(
                assistant_parse_failure_text(
                    result.reply or draft_preview,
                    hint="Не удалось разобрать ответ помощника. Попробуй ещё раз.",
                ),
            )
            return
        await render_proposal(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            reply=result.reply,
            document=result.document,
            telegram_user_id=callback.from_user.id,
        )

    @router.callback_query(F.data == "sess_gen_ok")
    async def handle_sess_gen_ok(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        result = await mediator.send(ApproveProposalCommand(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        if result.blocked_empty:
            text = jinja_env.get_template("proposal_empty_blocked.j2").render()
            if callback.message:
                await callback.message.answer(text)
            await callback.answer()
            return
        if result.blocked_unresolved:
            text = jinja_env.get_template("proposal_unresolved_blocked.j2").render()
            if result.document is not None:
                await render_next_session_proposal(
                    jinja_env=jinja_env,
                    message=callback.message,
                    reply=text,
                    document=result.document,
                    telegram_user_id=callback.from_user.id,
                )
                await callback.answer()
            else:
                if callback.message:
                    await callback.message.answer(text)
                await callback.answer()
            return
        today = await mediator.send(GetTodayWorkoutQuery(telegram_user_id=callback.from_user.id))
        chat = _chat_message(callback.message)
        if chat is not None:
            if today.document is not None:
                await _show_session_card(
                    mediator=mediator,
                    message=chat,
                    document=today.document,
                )
            else:
                await chat.answer("Сессия начата.", reply_markup=home_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "sess_edit")
    async def handle_sess_edit(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.PROPOSAL_UTTERANCE,
                expected_field="workout_edit",
            ),
        )
        if callback.message:
            await callback.message.answer("Напиши или продиктуй голосом, что поменять в сегодняшней тренировке.")
        await callback.answer()

    @router.callback_query(F.data.startswith("sess_pick:"))
    async def handle_sess_pick(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        _, slot_s, exercise_s = callback.data.split(":", 2)
        pending = await mediator.send(GetPendingProposalQuery(telegram_user_id=callback.from_user.id))
        day_position = 1
        if pending.document is not None and pending.document.days:
            day_position = pending.document.days[0].position
        result = await mediator.send(
            SelectExerciseForProposalCommand(
                telegram_user_id=callback.from_user.id,
                day_position=day_position,
                slot_position=int(slot_s),
                exercise_id=UUID(exercise_s),
            ),
        )
        if callback.message:
            await render_workout_edit_proposal(
                jinja_env=jinja_env,
                mediator=mediator,
                message=callback.message,
                document=result.document,
                telegram_user_id=callback.from_user.id,
            )
        await callback.answer()

    @router.callback_query(F.data == "sess_edit_ok")
    async def handle_sess_edit_ok(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        result = await mediator.send(ApproveProposalCommand(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        if result.blocked_empty:
            text = jinja_env.get_template("proposal_empty_blocked.j2").render()
            if callback.message:
                await callback.message.answer(text)
            await callback.answer()
            return
        if result.blocked_unresolved:
            text = jinja_env.get_template("proposal_unresolved_blocked.j2").render()
            if result.document is not None:
                await render_workout_edit_proposal(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=callback.message,
                    reply=text,
                    document=result.document,
                    telegram_user_id=callback.from_user.id,
                )
                await callback.answer()
            else:
                if callback.message:
                    await callback.message.answer(text)
                await callback.answer()
            return
        today = await mediator.send(GetTodayWorkoutQuery(telegram_user_id=callback.from_user.id))
        chat = _chat_message(callback.message)
        if chat is not None:
            if today.document is not None:
                await _show_session_card(
                    mediator=mediator,
                    message=chat,
                    document=today.document,
                )
            else:
                await chat.answer("Правка сохранена.", reply_markup=home_keyboard())
        await callback.answer()

    @router.callback_query(F.data.startswith("slot:"))
    async def handle_slot(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        position_raw = callback.data.split(":", 1)[1]
        if not position_raw.isdigit():
            await callback.answer()
            return
        position = int(position_raw)
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        if callback.message is None:
            await callback.answer()
            return
        await _show_slot_screen(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            position=position,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_card:"))
    async def handle_slot_card(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        position_raw = callback.data.split(":", 1)[1]
        if not position_raw.isdigit() or callback.message is None:
            await callback.answer()
            return
        found = await _find_session_slot(
            mediator,
            telegram_user_id=callback.from_user.id,
            position=int(position_raw),
        )
        if found is None:
            await callback.answer("Упражнение не найдено.", show_alert=True)
            return
        _, slot = found
        await _edit_live_exercise_card(callback.message, mediator=mediator, slot=slot)
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_alt:"))
    async def handle_slot_alt(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        parts = callback.data.split(":")
        if callback.message is None or len(parts) < 2 or not parts[1].isdigit():
            await callback.answer()
            return
        offset = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        alert = await show_similar_exercises(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            position=int(parts[1]),
            offset=offset,
        )
        if alert is not None:
            await callback.answer(alert, show_alert=True)
            return
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_swap:"))
    async def handle_slot_swap(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        parsed = _parse_slot_swap(callback.data)
        if parsed is None or callback.message is None or getattr(callback.message, "edit_text", None) is None:
            await callback.answer()
            return
        position, exercise_id = parsed
        try:
            result = await mediator.send(
                SwapSessionSlotExerciseCommand(
                    telegram_user_id=callback.from_user.id,
                    slot_position=position,
                    exercise_id=exercise_id,
                ),
            )
        except DomainError:
            found = await _find_session_slot(
                mediator,
                telegram_user_id=callback.from_user.id,
                position=position,
            )
            if found is not None:
                await _edit_live_exercise_card(callback.message, mediator=mediator, slot=found[1])
            await callback.answer(
                "Не получилось заменить: замена возможна во время тренировки и до записи подходов.",
                show_alert=True,
            )
            return
        await _edit_live_exercise_card(callback.message, mediator=mediator, slot=result.slot)
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_swap_prog:"))
    async def handle_slot_swap_prog(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        await callback.answer()
        if not isinstance(callback.message, Message):
            return
        position = int(callback.data.split(":", 1)[1])
        try:
            result = await mediator.send(
                ReplaceProgramSlotFromSessionCommand(telegram_user_id=callback.from_user.id, slot_position=position),
            )
        except DomainError:
            await callback.message.answer(
                "Не получилось обновить программу: эта тренировка не совпадает с днём активной программы.",
                reply_markup=back_to_slot_keyboard(position=position),
            )
            return
        await _show_slot_screen(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            position=position,
            prefix=f"📋 Готово: в программе в дне «{html.escape(result.day_title)}» теперь это упражнение.",
        )

    @router.callback_query(F.data.startswith("slot_how:"))
    async def handle_slot_how(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        position = int(callback.data.split(":", 1)[1])
        today = await mediator.send(GetTodayWorkoutQuery(telegram_user_id=callback.from_user.id))
        if callback.message is None or today.document is None:
            await callback.answer()
            return
        slot = next(
            (item for day in today.document.days for item in day.slots if item.position == position),
            None,
        )
        if slot is None or slot.exercise_id is None:
            if callback.message:
                await callback.message.answer("Сначала выбери упражнение из каталога.")
            await callback.answer()
            return
        guide = await mediator.send(GetExerciseGuideQuery(exercise_id=slot.exercise_id))
        if not guide.found:
            if callback.message:
                await callback.message.answer("Не нашёл технику для этого упражнения.")
            await callback.answer()
            return
        text = jinja_env.get_template("exercise_guide.j2").render(
            name=guide.name,
            technique=guide.technique,
            videos=[{"platform": item.platform, "url": item.url, "title": item.title} for item in guide.videos],
        )
        if callback.message:
            await callback.message.answer(
                text,
                reply_markup=exercise_guide_keyboard(
                    videos=[(item.platform, item.url, item.title) for item in guide.videos],
                    back_callback=f"slot:{position}",
                ),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_plan:"))
    async def handle_slot_plan(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        position = int(callback.data.split(":", 1)[1])
        try:
            result = await mediator.send(
                ConfirmExerciseAsPlannedCommand(
                    telegram_user_id=callback.from_user.id,
                    slot_position=position,
                ),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось отметить: {exc}")
            await callback.answer()
            return
        if callback.message is not None:
            await _edit_exercise_card(
                callback.message,
                mediator=mediator,
                slot=result.slot,
                confirmed=True,
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_undo:"))
    async def handle_slot_undo(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        position = int(callback.data.split(":", 1)[1])
        try:
            result = await mediator.send(
                ClearSlotActualCommand(
                    telegram_user_id=callback.from_user.id,
                    slot_position=position,
                ),
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось снять отметку: {exc}")
            await callback.answer()
            return
        if callback.message is not None:
            await _edit_exercise_card(
                callback.message,
                mediator=mediator,
                slot=result.slot,
                confirmed=False,
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_fact:"))
    async def handle_slot_fact(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        position = int(callback.data.split(":", 1)[1])
        if callback.message is None:
            await callback.answer()
            return
        await _ask_slot_weight(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            position=position,
            card_message_id=_card_message_id(callback.message),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_w_plan:"))
    async def handle_slot_w_plan(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        position = int(callback.data.split(":", 1)[1])
        if callback.message is None:
            await callback.answer()
            return
        found = await _find_session_slot(
            mediator,
            telegram_user_id=callback.from_user.id,
            position=position,
        )
        if found is None:
            if callback.message:
                await callback.message.answer("Упражнение не найдено.")
            await callback.answer()
            return
        _, slot = found
        workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=callback.from_user.id))
        _, card_message_id = _parse_draft_field(workflow.expected_field)
        await _ask_slot_load(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            position=position,
            weight_kg=slot.weight_kg,
            card_message_id=card_message_id,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_w_none:"))
    async def handle_slot_w_none(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        position = int(callback.data.split(":", 1)[1])
        if callback.message is None:
            await callback.answer()
            return
        workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=callback.from_user.id))
        _, card_message_id = _parse_draft_field(workflow.expected_field)
        await _ask_slot_load(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            position=position,
            weight_kg=None,
            card_message_id=card_message_id,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_r_plan:"))
    async def handle_slot_r_plan(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        position = int(callback.data.split(":", 1)[1])
        if callback.message is None:
            await callback.answer()
            return
        workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=callback.from_user.id))
        weight_kg, card_message_id = _parse_draft_field(workflow.expected_field)
        found = await _find_session_slot(
            mediator,
            telegram_user_id=callback.from_user.id,
            position=position,
        )
        if found is None:
            if callback.message:
                await callback.message.answer("Упражнение не найдено.")
            await callback.answer()
            return
        _, slot = found
        try:
            await _record_slot_actual(
                mediator=mediator,
                message=callback.message,
                telegram_user_id=callback.from_user.id,
                position=position,
                weight_kg=weight_kg,
                reps=slot.reps,
                duration_seconds=slot.duration_seconds,
                card_message_id=card_message_id,
            )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось сохранить: {exc}")
            await callback.answer()
            return
        await callback.answer()

    @router.callback_query(F.data.startswith("slot_video:"))
    async def handle_slot_video(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        position = int(callback.data.split(":", 1)[1])
        today = await mediator.send(GetTodayWorkoutQuery(telegram_user_id=callback.from_user.id))
        if today.document is None or today.session_status is None:
            if callback.message:
                await callback.message.answer("Нет открытой тренировки.")
            await callback.answer()
            return
        if today.session_status != SessionStatus.IN_PROGRESS:
            if callback.message:
                await callback.message.answer("Видео упражнения можно записать только во время тренировки.")
            await callback.answer()
            return
        slot = next(
            (item for day in today.document.days for item in day.slots if item.position == position),
            None,
        )
        if slot is None or slot.actual is None:
            if callback.message:
                await callback.message.answer("Сначала запиши факт по упражнению.")
            await callback.answer()
            return
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.TECHNIQUE_VIDEO,
                focus_slot=position,
            ),
        )
        if callback.message:
            await callback.message.answer("Пришли видео упражнения (до 20 МБ).")
        await callback.answer()

    @router.callback_query(F.data == "slot_ok")
    async def handle_slot_ok(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        result = await mediator.send(ApproveProposalCommand(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        if result.blocked_empty or result.blocked_unresolved:
            if callback.message:
                await callback.message.answer("Факт не подтверждён. Проверь упражнение и попробуй ещё раз.")
            await callback.answer()
            return
        today = await mediator.send(GetTodayWorkoutQuery(telegram_user_id=callback.from_user.id))
        chat = _chat_message(callback.message)
        if today.document is not None and chat is not None:
            await _show_session_card(
                mediator=mediator,
                message=chat,
                document=today.document,
            )
        await callback.answer()

    @router.callback_query(F.data == "sess_all")
    async def handle_sess_all(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        try:
            await mediator.send(BeginSessionCompletionCommand(telegram_user_id=callback.from_user.id))
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось завершить: {exc}")
            await callback.answer()
            return
        text = jinja_env.get_template("session_completion.j2").render()
        if callback.message:
            await callback.message.answer(text, reply_markup=completion_prompt_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "sess_restart")
    async def handle_sess_restart(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer()
            return
        text = jinja_env.get_template("session_restart_confirm.j2").render()
        if callback.message:
            await callback.message.answer(text, reply_markup=session_restart_confirm_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "sess_restart_ok")
    async def handle_sess_restart_ok(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        try:
            result = await mediator.send(RestartOpenSessionCommand(telegram_user_id=callback.from_user.id))
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось начать заново: {exc}")
            await callback.answer()
            return
        chat = _chat_message(callback.message)
        if chat is None:
            await callback.answer()
            return
        await _show_session_card(
            mediator=mediator,
            message=chat,
            document=result.document,
        )
        await callback.answer()

    async def _finalize_and_report(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        try:
            result = await mediator.send(FinalizeSessionCommand(telegram_user_id=callback.from_user.id))
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось сохранить: {exc}")
            await callback.answer()
            return
        if callback.message:
            text = await _render_document_template(
                jinja_env=jinja_env,
                mediator=mediator,
                template_name="session_completed.j2",
                document=result.document,
            )
            await callback.message.answer(text, reply_markup=home_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "sess_plan_all")
    async def handle_sess_plan_all(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        today = await mediator.send(GetTodayWorkoutQuery(telegram_user_id=callback.from_user.id))
        if today.document is None:
            if callback.message:
                await callback.message.answer("Нет открытой тренировки.")
            await callback.answer()
            return
        try:
            for day in today.document.days:
                for slot in sorted(day.slots, key=lambda item: item.position):
                    if slot.actual is not None:
                        continue
                    await mediator.send(
                        ConfirmExerciseAsPlannedCommand(
                            telegram_user_id=callback.from_user.id,
                            slot_position=slot.position,
                        ),
                    )
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось отметить: {exc}")
            await callback.answer()
            return
        await _finalize_and_report(callback)

    @router.callback_query(F.data == "sess_fin")
    async def handle_sess_fin(callback: CallbackQuery) -> None:
        await _finalize_and_report(callback)

    @router.callback_query(F.data == "sess_fin_ok")
    async def handle_sess_fin_ok(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        result = await mediator.send(ApproveProposalCommand(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        if result.blocked_empty or result.blocked_unresolved:
            if callback.message:
                await callback.message.answer("Правку факта подтвердить нельзя. Скажи иначе или жми «Готово».")
            await callback.answer()
            return
        try:
            finalized = await mediator.send(FinalizeSessionCommand(telegram_user_id=callback.from_user.id))
        except DomainError as exc:
            if callback.message:
                await callback.message.answer(f"Не удалось завершить: {exc}")
            await callback.answer()
            return
        text = await _render_document_template(
            jinja_env=jinja_env,
            mediator=mediator,
            template_name="session_completed.j2",
            document=finalized.document,
        )
        if callback.message:
            await callback.message.answer(text, reply_markup=home_keyboard())
        await callback.answer()

    return router


async def handle_slot_weight_utterance(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    text: str,
    focus_slot: int | None,
) -> None:
    assert message.from_user is not None
    if focus_slot is None:
        await message.answer("Сначала открой упражнение в тренировке.")
        return
    try:
        weight_kg = _parse_weight_kg(text)
    except ValueError as exc:
        await message.answer(f"{exc}. Напиши вес в кг или 0.")
        return
    workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=message.from_user.id))
    _, card_message_id = _parse_draft_field(workflow.expected_field)
    await _ask_slot_load(
        jinja_env=jinja_env,
        mediator=mediator,
        message=message,
        telegram_user_id=message.from_user.id,
        position=focus_slot,
        weight_kg=weight_kg,
        card_message_id=card_message_id,
    )


async def handle_slot_load_utterance(
    *,
    mediator: RequestMediator,
    message: Message,
    text: str,
    focus_slot: int | None,
    draft_weight: str | None,
) -> None:
    assert message.from_user is not None
    if focus_slot is None:
        await message.answer("Сначала открой упражнение в тренировке.")
        return
    found = await _find_session_slot(
        mediator,
        telegram_user_id=message.from_user.id,
        position=focus_slot,
    )
    if found is None:
        await message.answer("Упражнение не найдено.")
        return
    _, slot = found
    uses_duration = slot.duration_seconds is not None
    try:
        if uses_duration:
            duration_seconds = _parse_positive_int(text, label="секунды")
            reps = None
        else:
            reps = _parse_positive_int(text, label="повторы")
            duration_seconds = None
    except ValueError as exc:
        await message.answer(str(exc))
        return
    try:
        weight_kg, card_message_id = _parse_draft_field(draft_weight)
        await _record_slot_actual(
            mediator=mediator,
            message=message,
            telegram_user_id=message.from_user.id,
            position=focus_slot,
            weight_kg=weight_kg,
            reps=reps,
            duration_seconds=duration_seconds,
            card_message_id=card_message_id,
        )
    except DomainError as exc:
        await message.answer(f"Не удалось сохранить: {exc}")


async def handle_workout_edit_utterance(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    text: str,
) -> None:
    assert message.from_user is not None
    draft_preview = ""
    async with message_draft_scope(message.bot, message.chat.id) as draft:
        result = await mediator.send(
            ProposeWorkoutChangeCommand(telegram_user_id=message.from_user.id, utterance=text),
        )
        draft_preview = draft.preview_text
    if result.agent_unavailable:
        await message.answer(jinja_env.get_template("agent_unavailable.j2").render(), reply_markup=home_keyboard())
        return
    if result.schema_failed or result.document is None:
        await message.answer(
            assistant_parse_failure_text(result.reply or draft_preview),
            reply_markup=workout_edit_actions_keyboard(can_approve=False),
        )
        return
    await render_workout_edit_proposal(
        jinja_env=jinja_env,
        mediator=mediator,
        message=message,
        reply=result.reply,
        document=result.document,
        telegram_user_id=message.from_user.id,
    )


async def handle_slot_actual_utterance(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    text: str,
) -> None:
    assert message.from_user is not None
    draft_preview = ""
    async with message_draft_scope(message.bot, message.chat.id) as draft:
        result = await mediator.send(
            ProposeSlotActualCommand(telegram_user_id=message.from_user.id, utterance=text),
        )
        draft_preview = draft.preview_text
    if result.agent_unavailable:
        await message.answer(jinja_env.get_template("agent_unavailable.j2").render(), reply_markup=home_keyboard())
        return
    if result.schema_failed or result.document is None:
        await message.answer(
            assistant_parse_failure_text(
                result.reply or draft_preview,
                hint="Не удалось разобрать факт. Скажи иначе.",
            ),
        )
        return
    await render_performance_proposal(
        jinja_env=jinja_env,
        mediator=mediator,
        message=message,
        reply=result.reply,
        document=result.document,
        slot_position=result.slot_position,
        telegram_user_id=message.from_user.id,
    )


async def handle_completion_deviation_utterance(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    text: str,
) -> None:
    assert message.from_user is not None
    draft_preview = ""
    async with message_draft_scope(message.bot, message.chat.id) as draft:
        result = await mediator.send(
            ProposeSessionDeviationCommand(telegram_user_id=message.from_user.id, utterance=text),
        )
        draft_preview = draft.preview_text
    if result.agent_unavailable:
        await message.answer(jinja_env.get_template("agent_unavailable.j2").render(), reply_markup=home_keyboard())
        return
    if result.schema_failed or result.document is None:
        await message.answer(
            assistant_parse_failure_text(
                result.reply or draft_preview,
                hint="Не удалось разобрать отклонения. Скажи иначе.",
            ),
        )
        return
    await render_completion_deviation_proposal(
        jinja_env=jinja_env,
        message=message,
        reply=result.reply,
        document=result.document,
        telegram_user_id=message.from_user.id,
    )
