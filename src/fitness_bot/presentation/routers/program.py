from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import ExpectedInput, ProgramType, ProposalKind
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.program_catalog import (
    PROGRAM_TYPE_COPY,
    TRAINING_STYLE_COPY,
    structure_choice_items,
    training_style_label,
)
from fitness_bot.domain.workout.document import (
    ExerciseSlot,
    WorkoutDay,
    WorkoutDocument,
    is_matchable_custom_request,
    unresolved_slot_refs,
)
from fitness_bot.presentation.keyboards import (
    INTENSITY_LABELS,
    PROGRAM_TYPE_LABELS,
    TRAINING_STYLE_LABELS,
    WEEKDAY_LABELS,
    exercise_guide_keyboard,
    home_keyboard,
    match_exercises_keyboard,
    program_after_type_keyboard,
    program_day_keyboard,
    program_edit_menu_keyboard,
    program_screen_keyboard,
    program_slot_keyboard,
    program_type_keyboard,
    proposal_actions_keyboard,
    proposal_day_keyboard,
    proposal_slot_keyboard,
    proposal_slot_load_keyboard,
    proposal_slot_weight_keyboard,
)
from fitness_bot.presentation.message_draft import assistant_parse_failure_text, message_draft_scope
from fitness_bot.presentation.muscle_emoji import build_slot_nav_items
from fitness_bot.service.models.commands.program import (
    ApproveProposalCommand,
    ChooseProgramTypeCommand,
    DiscardProposalCommand,
    ProposeProgramChangeCommand,
    ProposeProgramCommand,
    SelectExerciseForProposalCommand,
    UpdateProposalSlotPlannedCommand,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.match_exercises import (
    GetExerciseGuideQuery,
    GetExerciseNamesQuery,
    MatchExercisesQuery,
)
from fitness_bot.service.models.queries.program import GetActiveProgramQuery, GetPendingProposalQuery
from fitness_bot.service.models.queries.users import GetWorkflowQuery


def _weekday_label(weekday: int | None) -> str | None:
    if weekday is None:
        return None
    return WEEKDAY_LABELS.get(weekday)


def _intensity_label(intensity: object) -> str:
    value = getattr(intensity, "value", intensity)
    return INTENSITY_LABELS.get(str(value), str(value))


def _training_style_day_label(day: WorkoutDay) -> str:
    return training_style_label(day.training_style)


def _day_button_label(day: WorkoutDay) -> str:
    wd = _weekday_label(day.weekday)
    intensity = _intensity_label(day.intensity)
    style = _training_style_day_label(day)
    if wd:
        return f"день {day.position} · {wd} · {intensity} · {style}"
    return f"день {day.position} · без дня недели · {intensity} · {style}"


def _slot_button_items(
    day: WorkoutDay,
    names: dict[UUID, str],
) -> list[tuple[int, str]]:
    return build_slot_nav_items(day.slots, names=names)


def _schedule_complete(document: WorkoutDocument) -> bool:
    try:
        document.assert_schedule_complete()
        return True
    except DomainError:
        return False


def _can_approve_program(document: WorkoutDocument) -> bool:
    try:
        document.assert_approvable(require_schedule=True)
        return True
    except DomainError:
        return False


def _day_buttons(document: WorkoutDocument) -> list[tuple[int, str]]:
    return [(day.position, _day_button_label(day)) for day in document.days]


def _program_type_render_context(
    *,
    program_type: ProgramType | str | None,
    document: WorkoutDocument | None = None,
) -> dict[str, str]:
    type_value = program_type.value if isinstance(program_type, ProgramType) else (program_type or "")
    if not type_value and document is not None:
        type_value = document.program_type.value
    type_copy = PROGRAM_TYPE_COPY.get(ProgramType(type_value)) if type_value else None
    return {
        "program_type_label": type_copy.label if type_copy else PROGRAM_TYPE_LABELS.get(type_value, type_value),
        "program_type_blurb": type_copy.blurb if type_copy else "",
    }


def _day_style_view(day: WorkoutDay) -> dict[str, str]:
    copy = TRAINING_STYLE_COPY.get(day.training_style)
    label = copy.label if copy else TRAINING_STYLE_LABELS.get(day.training_style.value, day.training_style.value)
    return {
        "training_style_label": label,
        "training_style_blurb": copy.blurb if copy else "",
        "training_style_summary": copy.summary if copy else "",
    }


async def _answer_structure_menu(
    *,
    jinja_env: Environment,
    message: Message,
    telegram_user_id: int | None = None,
    intro: str | None = None,
) -> None:
    text = jinja_env.get_template("program_structure_menu.j2").render(
        structure_items=structure_choice_items(),
    )
    if intro:
        text = f"{intro}\n\n{text}"
    await message.answer(text, reply_markup=program_type_keyboard())


def _is_program_draft(pending: object) -> bool:
    return bool(
        getattr(pending, "proposal_id", None)
        and getattr(pending, "has_document", False)
        and getattr(pending, "document", None) is not None
        and getattr(pending, "kind", None) == ProposalKind.PROGRAM,
    )


async def _render_active_program(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    active: object,
    has_pending: bool,
    telegram_user_id: int | None = None,
    status_line: str | None = None,
) -> None:
    names = await _load_exercise_names(mediator)
    document = active.document
    assert document is not None
    assert active.program_type is not None
    text = jinja_env.get_template("workout.j2").render(
        document=_document_view(document, names),
        has_pending=has_pending,
        **_program_type_render_context(
            program_type=active.program_type,
            document=document,
        ),
    )
    if status_line:
        text = f"{status_line}\n\n{text}"
    await message.answer(
        text,
        reply_markup=program_screen_keyboard(
            has_pending=has_pending,
            has_active=True,
            days=_day_buttons(document),
        ),
    )


def _slot_view(slot: ExerciseSlot, names: dict[UUID, str]) -> dict:
    return {
        "position": slot.position,
        "exercise_id": str(slot.exercise_id) if slot.exercise_id else None,
        "exercise_name": names.get(slot.exercise_id) if slot.exercise_id else None,
        "custom_request": slot.custom_request,
        "muscle_group": slot.muscle_group,
        "sets": slot.sets,
        "reps": slot.reps,
        "duration_seconds": slot.duration_seconds,
        "weight_kg": slot.weight_kg,
        "rest_seconds": slot.rest_seconds,
        "rpe": slot.rpe,
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
                **_day_style_view(day),
                "slots": [_slot_view(slot, name_map) for slot in day.slots],
            }
            for day in document.days
        ],
    }


def _day_view(day: WorkoutDay, names: dict[UUID, str] | None = None) -> dict:
    name_map = names or {}
    return {
        "weekday": day.weekday,
        "weekday_label": _weekday_label(day.weekday),
        "title": day.title,
        "position": day.position,
        "intensity": day.intensity.value,
        "intensity_label": _intensity_label(day.intensity),
        "warmup": day.warmup,
        "cooldown": day.cooldown,
        **_day_style_view(day),
        "slots": [_slot_view(slot, name_map) for slot in day.slots],
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


async def render_proposal(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    reply: str = "",
    document: WorkoutDocument | None = None,
    program_type: ProgramType | None = None,
    telegram_user_id: int | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    names = await _load_exercise_names(mediator) if document is not None else {}
    missing_weekdays = False
    if document is not None:
        missing_weekdays = not _schedule_complete(document)
    text = jinja_env.get_template("proposal.j2").render(
        reply=reply,
        document=_document_view(document, names) if document else None,
        missing_weekdays=missing_weekdays,
        **_program_type_render_context(
            program_type=program_type,
            document=document,
        ),
    )
    can_approve = document is not None and _can_approve_program(document)
    markup = reply_markup
    if markup is None:
        markup = proposal_actions_keyboard(
            can_approve=can_approve,
            days=_day_buttons(document) if document is not None else None,
            can_save_to_library=document is not None,
        )
    await message.answer(text, reply_markup=markup)

    if document is None:
        return
    for day_position, slot_position, custom_request, muscle_group in unresolved_slot_refs(document):
        if not is_matchable_custom_request(custom_request):
            continue
        matches = await mediator.send(
            MatchExercisesQuery(query=custom_request, muscle=muscle_group, limit=5),
        )
        if not matches.items:
            await message.answer(f"Для «{custom_request}» совпадений в каталоге нет. Переформулируй текстом.")
            continue
        await message.answer(
            f"Выбери упражнение для дня {day_position}, слот {slot_position}:",
            reply_markup=match_exercises_keyboard(
                day_position=day_position,
                slot_position=slot_position,
                items=[(str(item.exercise_id), item.name) for item in matches.items],
            ),
        )


async def render_proposal_day(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    document: WorkoutDocument,
    day_position: int,
    reply: str = "",
    telegram_user_id: int | None = None,
) -> None:
    day = next((item for item in document.days if item.position == day_position), None)
    if day is None:
        await message.answer("День не найден в черновике.")
        return
    names = await _load_exercise_names(mediator)
    text = jinja_env.get_template("proposal_day.j2").render(day=_day_view(day, names), reply=reply)
    await message.answer(
        text,
        reply_markup=proposal_day_keyboard(
            day_position=day_position,
            slots=_slot_button_items(day, names),
        ),
    )


def _format_kg(value: object) -> str | None:
    if value is None:
        return None
    from decimal import Decimal

    text = format(Decimal(str(value)).normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _planned_load_label(slot: ExerciseSlot) -> str:
    if slot.duration_seconds is not None:
        return f"{slot.duration_seconds}с"
    return f"{slot.reps} повт."


def encode_proposal_planned_field(day_position: int, weight_encoded: str | None = None) -> str:
    if weight_encoded is None:
        return f"proposal_planned:{day_position}"
    return f"proposal_planned:{day_position}:{weight_encoded}"


def parse_proposal_planned_field(field: str | None) -> tuple[int, str | None] | None:
    if not field or not field.startswith("proposal_planned:"):
        return None
    parts = field.split(":", 2)
    if len(parts) < 2:
        return None
    try:
        day_position = int(parts[1])
    except ValueError:
        return None
    weight_part = parts[2] if len(parts) == 3 else None
    return day_position, weight_part


async def _find_proposal_slot(
    mediator: RequestMediator,
    *,
    telegram_user_id: int,
    day_position: int,
    slot_position: int,
) -> tuple[WorkoutDocument, WorkoutDay, ExerciseSlot] | None:
    pending = await mediator.send(GetPendingProposalQuery(telegram_user_id=telegram_user_id))
    if pending.document is None:
        return None
    day = next((item for item in pending.document.days if item.position == day_position), None)
    if day is None:
        return None
    slot = next((item for item in day.slots if item.position == slot_position), None)
    if slot is None:
        return None
    return pending.document, day, slot


async def render_proposal_slot(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    day_position: int,
    slot_position: int,
) -> None:
    found = await _find_proposal_slot(
        mediator,
        telegram_user_id=telegram_user_id,
        day_position=day_position,
        slot_position=slot_position,
    )
    if found is None:
        await message.answer("Упражнение не найдено в черновике.")
        return
    _, _, slot = found
    names = await _load_exercise_names(mediator)
    text = jinja_env.get_template("program_slot.j2").render(slot=_slot_view(slot, names))
    await message.answer(
        text,
        reply_markup=proposal_slot_keyboard(
            day_position=day_position,
            slot_position=slot_position,
            has_catalog_guide=slot.exercise_id is not None,
        ),
    )


async def ask_proposal_slot_weight(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    day_position: int,
    slot_position: int,
) -> None:
    found = await _find_proposal_slot(
        mediator,
        telegram_user_id=telegram_user_id,
        day_position=day_position,
        slot_position=slot_position,
    )
    if found is None:
        await message.answer("Упражнение не найдено в черновике.")
        return
    _, _, slot = found
    names = await _load_exercise_names(mediator)
    planned_weight = _format_kg(slot.weight_kg)
    await mediator.send(
        ExpectInputCommand(
            telegram_user_id=telegram_user_id,
            expected_input=ExpectedInput.SLOT_WEIGHT,
            expected_field=encode_proposal_planned_field(day_position),
            focus_slot=slot_position,
        ),
    )
    text = jinja_env.get_template("slot_ask_weight.j2").render(
        position=slot_position,
        exercise_name=names.get(slot.exercise_id) if slot.exercise_id else slot.custom_request,
        planned_weight_kg=planned_weight,
    )
    await message.answer(
        text,
        reply_markup=proposal_slot_weight_keyboard(
            day_position=day_position,
            slot_position=slot_position,
            planned_weight_kg=planned_weight,
        ),
    )


async def ask_proposal_slot_load(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    day_position: int,
    slot_position: int,
    weight_kg: object,
) -> None:
    from decimal import Decimal

    found = await _find_proposal_slot(
        mediator,
        telegram_user_id=telegram_user_id,
        day_position=day_position,
        slot_position=slot_position,
    )
    if found is None:
        await message.answer("Упражнение не найдено в черновике.")
        return
    _, _, slot = found
    names = await _load_exercise_names(mediator)
    weight_value = None if weight_kg is None else Decimal(str(weight_kg))
    weight_encoded = "" if weight_value is None else str(weight_value)
    uses_duration = slot.duration_seconds is not None
    planned_label = _planned_load_label(slot)
    await mediator.send(
        ExpectInputCommand(
            telegram_user_id=telegram_user_id,
            expected_input=ExpectedInput.SLOT_LOAD,
            expected_field=encode_proposal_planned_field(day_position, weight_encoded),
            focus_slot=slot_position,
        ),
    )
    text = jinja_env.get_template("slot_ask_load.j2").render(
        position=slot_position,
        exercise_name=names.get(slot.exercise_id) if slot.exercise_id else slot.custom_request,
        uses_duration=uses_duration,
        planned_label=planned_label,
        weight_kg=_format_kg(weight_value),
    )
    await message.answer(
        text,
        reply_markup=proposal_slot_load_keyboard(
            day_position=day_position,
            slot_position=slot_position,
            planned_label=planned_label,
        ),
    )


async def save_proposal_slot_planned(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    telegram_user_id: int,
    day_position: int,
    slot_position: int,
    weight_kg: object,
    reps: int | None,
    duration_seconds: int | None,
) -> None:
    from decimal import Decimal

    weight_value = None if weight_kg is None else Decimal(str(weight_kg))
    try:
        result = await mediator.send(
            UpdateProposalSlotPlannedCommand(
                telegram_user_id=telegram_user_id,
                day_position=day_position,
                slot_position=slot_position,
                weight_kg=weight_value,
                reps=reps,
                duration_seconds=duration_seconds,
            ),
        )
    except DomainError as exc:
        await message.answer(f"Не удалось сохранить: {exc}")
        return
    await render_proposal_day(
        jinja_env=jinja_env,
        mediator=mediator,
        message=message,
        document=result.document,
        day_position=result.day_position,
        reply="Сохранил упражнение в черновике.",
        telegram_user_id=telegram_user_id,
    )


def create_program_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="program")

    @router.callback_query(F.data == "prog")
    async def handle_prog(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        active = await mediator.send(GetActiveProgramQuery(telegram_user_id=callback.from_user.id))
        pending = await mediator.send(GetPendingProposalQuery(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        has_program_draft = _is_program_draft(pending)
        if active.document is not None and active.program_type is not None:
            await _render_active_program(
                jinja_env=jinja_env,
                mediator=mediator,
                message=callback.message,
                active=active,
                has_pending=has_program_draft,
                telegram_user_id=callback.from_user.id,
            )
        elif has_program_draft:
            await render_proposal(
                jinja_env=jinja_env,
                mediator=mediator,
                message=callback.message,
                reply=pending.reply,
                document=pending.document,
                program_type=pending.program_type,
                telegram_user_id=callback.from_user.id,
            )
        else:
            intro = jinja_env.get_template("program_menu.j2").render()
            await _answer_structure_menu(
                jinja_env=jinja_env,
                message=callback.message,
                telegram_user_id=callback.from_user.id,
                intro=intro,
            )
        await callback.answer()

    @router.callback_query(F.data == "prog_edit_menu")
    async def handle_prog_edit_menu(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        pending = await mediator.send(GetPendingProposalQuery(telegram_user_id=callback.from_user.id))
        text = jinja_env.get_template("program_edit_menu.j2").render()
        if callback.message:
            await callback.message.answer(
                text,
                reply_markup=program_edit_menu_keyboard(has_pending=_is_program_draft(pending)),
            )
        await callback.answer()

    @router.callback_query(F.data == "prog_setup")
    async def handle_prog_setup(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        if callback.message is None:
            await callback.answer()
            return
        intro = jinja_env.get_template("program_menu.j2").render()
        await _answer_structure_menu(
            jinja_env=jinja_env,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            intro=intro,
        )
        await callback.answer()

    @router.callback_query(F.data == "prog_structure")
    async def handle_prog_structure(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        if callback.message is None:
            await callback.answer()
            return
        await _answer_structure_menu(
            jinja_env=jinja_env,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("prog_type:"))
    async def handle_prog_type(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        program_type = ProgramType(callback.data.split(":", 1)[1])
        await mediator.send(
            ChooseProgramTypeCommand(telegram_user_id=callback.from_user.id, program_type=program_type),
        )
        text = jinja_env.get_template("proposal.j2").render(
            reply="",
            document=None,
            missing_weekdays=False,
            **_program_type_render_context(program_type=program_type),
        )
        if callback.message:
            await callback.message.answer(text, reply_markup=program_after_type_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "prog_text")
    async def handle_prog_text(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.PROPOSAL_UTTERANCE,
                expected_field="program_edit",
            ),
        )
        if callback.message:
            if callback.message:
                await callback.message.answer(
                    "Опиши неделю текстом или голосовым: дни, мышцы, упражнения.\n"
                    "Например: «пн грудь-триц, ср спина-биц, пт ноги, по 5–6 упражнений».",
                )
            await callback.answer()

    @router.callback_query(F.data == "prog_gen")
    async def handle_prog_gen(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        if callback.message is None:
            await callback.answer()
            return
        await callback.answer()
        draft_preview = ""
        try:
            async with message_draft_scope(callback.bot, callback.message.chat.id) as draft:
                result = await mediator.send(ProposeProgramCommand(telegram_user_id=callback.from_user.id))
                draft_preview = draft.preview_text
        except DomainError as exc:
            await callback.message.answer(f"Не удалось предложить неделю: {exc}")
            return
        if result.agent_unavailable:
            text = jinja_env.get_template("agent_unavailable.j2").render()
            await callback.message.answer(text, reply_markup=home_keyboard())
            return
        if result.schema_failed or result.document is None:
            await callback.message.answer(
                assistant_parse_failure_text(
                    result.reply or draft_preview,
                    hint=(
                        "Не удалось разобрать ответ помощника. "
                        "Нажми «Пусть предложит» ещё раз или опиши неделю текстом."
                    ),
                ),
                reply_markup=program_after_type_keyboard(),
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

    @router.callback_query(F.data == "prog_draft")
    async def handle_prog_draft(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        pending = await mediator.send(GetPendingProposalQuery(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        if _is_program_draft(pending):
            await render_proposal(
                jinja_env=jinja_env,
                mediator=mediator,
                message=callback.message,
                reply=pending.reply,
                document=pending.document,
                program_type=pending.program_type,
                telegram_user_id=callback.from_user.id,
            )
        else:
            if callback.message:
                await callback.message.answer("Черновика программы сейчас нет.")
            await callback.answer()

    @router.callback_query(F.data.startswith("prog_day:"))
    async def handle_prog_day(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        day_position = int(callback.data.split(":", 1)[1])
        pending = await mediator.send(GetPendingProposalQuery(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        if pending.document is None:
            if callback.message:
                await callback.message.answer("Черновик не найден. Задай программу заново.")
            await callback.answer()
            return
        await render_proposal_day(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            document=pending.document,
            day_position=day_position,
            telegram_user_id=callback.from_user.id,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("pdraft_slot:"))
    async def handle_pdraft_slot(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        _, day_s, slot_s = callback.data.split(":", 2)
        if callback.message is None:
            await callback.answer()
            return
        await render_proposal_slot(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            day_position=int(day_s),
            slot_position=int(slot_s),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("pdraft_how:"))
    async def handle_pdraft_how(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        _, day_s, slot_s = callback.data.split(":", 2)
        day_position = int(day_s)
        slot_position = int(slot_s)
        if callback.message is None:
            await callback.answer()
            return
        found = await _find_proposal_slot(
            mediator,
            telegram_user_id=callback.from_user.id,
            day_position=day_position,
            slot_position=slot_position,
        )
        if found is None:
            if callback.message:
                await callback.message.answer("Упражнение не найдено в черновике.")
            await callback.answer()
            return
        _, _, slot = found
        if slot.exercise_id is None:
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
                    back_callback=f"pdraft_slot:{day_position}:{slot_position}",
                ),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("pdraft_edit:"))
    async def handle_pdraft_edit(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        _, day_s, slot_s = callback.data.split(":", 2)
        if callback.message is None:
            await callback.answer()
            return
        await ask_proposal_slot_weight(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            day_position=int(day_s),
            slot_position=int(slot_s),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("pdraft_w_plan:"))
    async def handle_pdraft_w_plan(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        _, day_s, slot_s = callback.data.split(":", 2)
        day_position = int(day_s)
        slot_position = int(slot_s)
        if callback.message is None:
            await callback.answer()
            return
        found = await _find_proposal_slot(
            mediator,
            telegram_user_id=callback.from_user.id,
            day_position=day_position,
            slot_position=slot_position,
        )
        if found is None:
            if callback.message:
                await callback.message.answer("Упражнение не найдено в черновике.")
            await callback.answer()
            return
        _, _, slot = found
        await ask_proposal_slot_load(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            day_position=day_position,
            slot_position=slot_position,
            weight_kg=slot.weight_kg,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("pdraft_w_none:"))
    async def handle_pdraft_w_none(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        _, day_s, slot_s = callback.data.split(":", 2)
        if callback.message is None:
            await callback.answer()
            return
        await ask_proposal_slot_load(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            day_position=int(day_s),
            slot_position=int(slot_s),
            weight_kg=None,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("pdraft_r_plan:"))
    async def handle_pdraft_r_plan(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        _, day_s, slot_s = callback.data.split(":", 2)
        day_position = int(day_s)
        slot_position = int(slot_s)
        if callback.message is None:
            await callback.answer()
            return
        workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=callback.from_user.id))
        parsed = parse_proposal_planned_field(workflow.expected_field)
        if parsed is None:
            if callback.message:
                await callback.message.answer("Сначала открой редактирование упражнения.")
            await callback.answer()
            return
        day_from_field, weight_raw = parsed
        found = await _find_proposal_slot(
            mediator,
            telegram_user_id=callback.from_user.id,
            day_position=day_position,
            slot_position=slot_position,
        )
        if found is None or day_from_field != day_position:
            if callback.message:
                await callback.message.answer("Упражнение не найдено в черновике.")
            await callback.answer()
            return
        _, _, slot = found
        weight_kg = None if not weight_raw else weight_raw
        await save_proposal_slot_planned(
            jinja_env=jinja_env,
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            day_position=day_position,
            slot_position=slot_position,
            weight_kg=weight_kg,
            reps=slot.reps,
            duration_seconds=slot.duration_seconds,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("prog_view_day:"))
    async def handle_prog_view_day(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        day_position = int(callback.data.split(":", 1)[1])
        active = await mediator.send(GetActiveProgramQuery(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        if active.document is None:
            if callback.message:
                await callback.message.answer("Активной программы нет.")
            await callback.answer()
            return
        day = next((item for item in active.document.days if item.position == day_position), None)
        if day is None:
            if callback.message:
                await callback.message.answer("День не найден.")
            await callback.answer()
            return
        names = await _load_exercise_names(mediator)
        text = jinja_env.get_template("workout_day.j2").render(day=_day_view(day, names))
        if callback.message:
            await callback.message.answer(
                text,
                reply_markup=program_day_keyboard(
                    day_position=day_position,
                    slots=_slot_button_items(day, names),
                ),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("prog_view_slot:"))
    async def handle_prog_view_slot(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        _, day_s, slot_s = callback.data.split(":", 2)
        day_position = int(day_s)
        slot_position = int(slot_s)
        active = await mediator.send(GetActiveProgramQuery(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        if active.document is None:
            if callback.message:
                await callback.message.answer("Активной программы нет.")
            await callback.answer()
            return
        day = next((item for item in active.document.days if item.position == day_position), None)
        if day is None:
            if callback.message:
                await callback.message.answer("День не найден.")
            await callback.answer()
            return
        slot = next((item for item in day.slots if item.position == slot_position), None)
        if slot is None:
            if callback.message:
                await callback.message.answer("Упражнение не найдено.")
            await callback.answer()
            return
        names = await _load_exercise_names(mediator)
        text = jinja_env.get_template("program_slot.j2").render(slot=_slot_view(slot, names))
        if callback.message:
            await callback.message.answer(
                text,
                reply_markup=program_slot_keyboard(
                    day_position=day_position,
                    slot_position=slot_position,
                    has_catalog_guide=slot.exercise_id is not None,
                ),
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("prog_view_how:"))
    async def handle_prog_view_how(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        _, day_s, slot_s = callback.data.split(":", 2)
        day_position = int(day_s)
        slot_position = int(slot_s)
        active = await mediator.send(GetActiveProgramQuery(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        if active.document is None:
            if callback.message:
                await callback.message.answer("Активной программы нет.")
            await callback.answer()
            return
        day = next((item for item in active.document.days if item.position == day_position), None)
        slot = None if day is None else next((item for item in day.slots if item.position == slot_position), None)
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
                    back_callback=f"prog_view_slot:{day_position}:{slot_position}",
                ),
            )
        await callback.answer()

    @router.callback_query(F.data == "prog_edit")
    async def handle_prog_edit(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.PROPOSAL_UTTERANCE,
                expected_field="program_edit",
            ),
        )
        if callback.message:
            if callback.message:
                await callback.message.answer("Напиши или продиктуй голосом, что поменять в неделе.")
            await callback.answer()

    @router.callback_query(F.data.startswith("prog_edit_day:"))
    async def handle_prog_edit_day(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        day_position = int(callback.data.split(":", 1)[1])
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.PROPOSAL_UTTERANCE,
                expected_field="program_edit_day",
                focus_slot=day_position,
            ),
        )
        if callback.message:
            if callback.message:
                await callback.message.answer("Напиши или продиктуй голосом, что поменять в этой тренировке.")
            await callback.answer()

    @router.callback_query(F.data.startswith("prog_pick:"))
    async def handle_prog_pick(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        _, day_s, slot_s, exercise_s = callback.data.split(":", 3)
        result = await mediator.send(
            SelectExerciseForProposalCommand(
                telegram_user_id=callback.from_user.id,
                day_position=int(day_s),
                slot_position=int(slot_s),
                exercise_id=UUID(exercise_s),
            ),
        )
        if callback.message:
            await render_proposal(
                jinja_env=jinja_env,
                mediator=mediator,
                message=callback.message,
                document=result.document,
                telegram_user_id=callback.from_user.id,
            )
        await callback.answer()

    @router.callback_query(F.data == "prog_ok")
    async def handle_prog_ok(callback: CallbackQuery) -> None:
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
        if result.blocked_schedule:
            text = jinja_env.get_template("proposal_schedule_blocked.j2").render()
            if result.document is not None:
                await render_proposal(
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
        if result.blocked_unresolved:
            text = jinja_env.get_template("proposal_unresolved_blocked.j2").render()
            if result.document is not None:
                await render_proposal(
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
        if result.library_program_id is not None and isinstance(callback.message, Message):
            from fitness_bot.presentation.routers.library import show_library_card

            await show_library_card(
                jinja_env=jinja_env,
                mediator=mediator,
                message=callback.message,
                bot=callback.bot,
                telegram_user_id=callback.from_user.id,
                program_id=result.library_program_id,
                status_line="💾 Изменения сохранены в карточку библиотеки. Активный план не менялся.",
            )
            await callback.answer()
            return
        text = jinja_env.get_template("program_active.j2").render()
        if callback.message:
            await callback.message.answer(text, reply_markup=home_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "prog_lib_save")
    async def handle_prog_lib_save(callback: CallbackQuery) -> None:
        from fitness_bot.presentation.routers.library import save_document_to_library

        assert callback.from_user is not None
        pending = await mediator.send(GetPendingProposalQuery(telegram_user_id=callback.from_user.id))
        if (
            pending.document is None
            or pending.kind != ProposalKind.PROGRAM
            or not isinstance(callback.message, Message)
        ):
            if callback.message:
                await callback.message.answer("Нет черновика программы для сохранения.")
            await callback.answer()
            return
        await save_document_to_library(
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            document=pending.document,
            intro="Сохранено в библиотеку как черновик. Черновик правки не сброшен — можно ещё сделать активной.",
            has_draft=True,
        )
        await callback.answer()

    @router.callback_query(F.data == "prog_lib_save_active")
    async def handle_prog_lib_save_active(callback: CallbackQuery) -> None:
        from fitness_bot.presentation.routers.library import save_document_to_library

        assert callback.from_user is not None
        active = await mediator.send(GetActiveProgramQuery(telegram_user_id=callback.from_user.id))
        if active.document is None or not isinstance(callback.message, Message):
            if callback.message:
                await callback.message.answer("Нет активной программы для сохранения.")
            await callback.answer()
            return
        await save_document_to_library(
            mediator=mediator,
            message=callback.message,
            telegram_user_id=callback.from_user.id,
            document=active.document,
            intro="Копия активной программы сохранена в библиотеку.",
        )
        await callback.answer()

    @router.callback_query(F.data == "draft_cancel")
    async def handle_draft_cancel(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await mediator.send(DiscardProposalCommand(telegram_user_id=callback.from_user.id))
        if callback.message is None:
            await callback.answer()
            return
        active = await mediator.send(GetActiveProgramQuery(telegram_user_id=callback.from_user.id))
        if active.document is not None and active.program_type is not None:
            await _render_active_program(
                jinja_env=jinja_env,
                mediator=mediator,
                message=callback.message,
                active=active,
                has_pending=False,
                telegram_user_id=callback.from_user.id,
                status_line="Черновик отменён.",
            )
            await callback.answer()
        else:
            if callback.message:
                await callback.message.answer("Черновик отменён.", reply_markup=home_keyboard())
            await callback.answer()

    return router


async def handle_proposal_utterance(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    message: Message,
    text: str,
    day_position: int | None = None,
) -> None:
    assert message.from_user is not None
    draft_preview = ""
    try:
        async with message_draft_scope(message.bot, message.chat.id) as draft:
            result = await mediator.send(
                ProposeProgramChangeCommand(
                    telegram_user_id=message.from_user.id,
                    utterance=text,
                    day_position=day_position,
                ),
            )
            draft_preview = draft.preview_text
    except DomainError as exc:
        scope = "тренировку" if day_position is not None else "неделю"
        await message.answer(f"Не получилось изменить {scope}: {exc}")
        return
    if result.agent_unavailable:
        await message.answer(jinja_env.get_template("agent_unavailable.j2").render(), reply_markup=home_keyboard())
        return
    if result.schema_failed or result.document is None:
        await message.answer(
            assistant_parse_failure_text(result.reply or draft_preview),
            reply_markup=proposal_actions_keyboard(can_approve=False),
        )
        return
    if result.day_position is not None:
        await render_proposal_day(
            jinja_env=jinja_env,
            mediator=mediator,
            message=message,
            document=result.document,
            day_position=result.day_position,
            reply=result.reply,
            telegram_user_id=message.from_user.id,
        )
        return
    await render_proposal(
        jinja_env=jinja_env,
        mediator=mediator,
        message=message,
        reply=result.reply,
        document=result.document,
        telegram_user_id=message.from_user.id,
    )
