from __future__ import annotations

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.body.wellbeing import WELLBEING_FRESHNESS_WINDOW
from fitness_bot.domain.enums import ExpectedInput, ProfileField, Supplement, WeightSource
from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.flow_helpers import (
    finish_profile_edit_if_active,
    show_info_offer,
    show_next_onboarding_step,
)
from fitness_bot.presentation.keyboards import body_saved_keyboard, wellbeing_saved_keyboard
from fitness_bot.presentation.routers.body import apply_weight_reminder_time
from fitness_bot.presentation.routers.feedback import handle_feedback_utterance
from fitness_bot.presentation.routers.library import (
    LIBRARY_EDIT_FIELD_PREFIX,
    LIBRARY_TITLE_FIELD_PREFIX,
    apply_library_title,
    handle_library_edit_utterance,
    library_field_program_id,
)
from fitness_bot.presentation.routers.program import (
    ask_proposal_slot_load,
    handle_proposal_utterance,
    parse_proposal_planned_field,
    save_proposal_slot_planned,
)
from fitness_bot.presentation.routers.progress_photo import apply_progress_photo_reminder_time
from fitness_bot.presentation.routers.session import (
    handle_completion_deviation_utterance,
    handle_slot_actual_utterance,
    handle_slot_load_utterance,
    handle_slot_weight_utterance,
    handle_workout_edit_utterance,
)
from fitness_bot.service.models.commands.body import (
    AddCustomMeasurementSiteCommand,
    RecordMeasurementCommand,
    RecordWeightCommand,
    RecordWellbeingCommand,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand, UpdateProfileCommand
from fitness_bot.service.models.queries.program import GetPendingProposalQuery
from fitness_bot.service.models.queries.users import GetProfileQuery, GetWorkflowQuery

_VOICE_FREE_TEXT_PROFILE_FIELDS = frozenset(
    {
        ProfileField.EQUIPMENT.value,
        ProfileField.LIMITATIONS.value,
        ProfileField.DIET_PREFS.value,
        ProfileField.NUTRITION_CONSTRAINTS.value,
        ProfileField.EXPERIENCE_DETAILS.value,
        ProfileField.PHARMA.value,
        "custom_measurement_name",
        "supplements_other",
    },
)


def voice_input_allowed(*, expected_input: ExpectedInput, expected_field: str | None) -> bool:
    """Voice is for free-text steps, not for numeric entry."""
    if expected_input in {
        ExpectedInput.PROPOSAL_UTTERANCE,
        ExpectedInput.COMPLETION_DEVIATION,
        ExpectedInput.COACH_APPLICATION,
        ExpectedInput.COACH_EDIT_CLIENT,
        ExpectedInput.MODERATOR_REJECT_COMMENT,
        ExpectedInput.FEEDBACK_TEXT,
        ExpectedInput.FEEDBACK_PHOTO,
        ExpectedInput.FEEDBACK_CANCEL_REPLY,
        ExpectedInput.WELLBEING,
    }:
        return True
    if expected_input == ExpectedInput.PROFILE_FIELD and expected_field in _VOICE_FREE_TEXT_PROFILE_FIELDS:
        return True
    if expected_input == ExpectedInput.PROFILE_FIELD and (expected_field or "").startswith(LIBRARY_TITLE_FIELD_PREFIX):
        return True
    return False


async def handle_user_utterance(
    *,
    message: Message,
    text: str,
    jinja_env: Environment,
    mediator: RequestMediator,
) -> None:
    """Shared text/voice path: route stripped utterance by expected_input."""
    assert message.from_user is not None
    text = text.strip()
    if not text:
        await message.answer("Пустой текст. Напиши или продиктуй ещё раз.")
        return

    workflow = await mediator.send(GetWorkflowQuery(telegram_user_id=message.from_user.id))

    if workflow.expected_input == ExpectedInput.NONE:
        await message.answer("Открой нужный раздел через меню.")
        return

    try:
        if await handle_feedback_utterance(
            message=message,
            text=text,
            mediator=mediator,
            expected_input=workflow.expected_input,
            expected_field=workflow.expected_field,
        ):
            return

        if workflow.expected_input == ExpectedInput.WEIGHT:
            await mediator.send(
                RecordWeightCommand(
                    telegram_user_id=message.from_user.id,
                    kilograms=text,
                    source=WeightSource.MANUAL,
                ),
            )
            await message.answer(
                "Вес сохранён.",
                reply_markup=body_saved_keyboard(back_callback="wt_menu", back_label="⬅️ К весу"),
            )
            return

        if workflow.expected_input == ExpectedInput.WELLBEING:
            recorded = await mediator.send(
                RecordWellbeingCommand(
                    telegram_user_id=message.from_user.id,
                    text=text,
                ),
            )
            reply = jinja_env.get_template("wellbeing_saved.j2").render(
                text=recorded.text,
                freshness_hours=int(WELLBEING_FRESHNESS_WINDOW.total_seconds() // 3600),
            )
            await message.answer(reply, reply_markup=wellbeing_saved_keyboard())
            return

        if workflow.expected_input == ExpectedInput.MEASUREMENT_VALUE:
            site_id = workflow.pending_site_id
            if site_id is None:
                raise DomainError("measurement site is not selected")
            await mediator.send(
                RecordMeasurementCommand(
                    telegram_user_id=message.from_user.id,
                    site_id=site_id,
                    centimeters=text,
                ),
            )
            await message.answer(
                "Обхват сохранён.",
                reply_markup=body_saved_keyboard(back_callback="meas_menu", back_label="📏 Ещё обхват"),
            )
            return

        if workflow.expected_input == ExpectedInput.PROFILE_FIELD:
            field_name = workflow.expected_field
            library_program_id = library_field_program_id(field_name, LIBRARY_TITLE_FIELD_PREFIX)
            if library_program_id is not None:
                await apply_library_title(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=message,
                    telegram_user_id=message.from_user.id,
                    program_id=library_program_id,
                    text=text,
                )
                return

            if field_name == "weight_reminder_time":
                await apply_weight_reminder_time(
                    mediator=mediator,
                    telegram_user_id=message.from_user.id,
                    text=text,
                )
                await mediator.send(
                    ExpectInputCommand(
                        telegram_user_id=message.from_user.id,
                        expected_input=ExpectedInput.NONE,
                    ),
                )
                await message.answer(
                    "Время напоминания сохранено.",
                    reply_markup=body_saved_keyboard(back_callback="wt_remind", back_label="⬅️ К напоминаниям"),
                )
                return

            if field_name == "progress_photo_reminder_time":
                await apply_progress_photo_reminder_time(
                    mediator=mediator,
                    telegram_user_id=message.from_user.id,
                    text=text,
                )
                await mediator.send(
                    ExpectInputCommand(
                        telegram_user_id=message.from_user.id,
                        expected_input=ExpectedInput.NONE,
                    ),
                )
                await message.answer(
                    "Время напоминания сохранено.",
                    reply_markup=body_saved_keyboard(back_callback="pp_remind", back_label="⬅️ К напоминаниям"),
                )
                return

            if field_name == "custom_measurement_name":
                result = await mediator.send(
                    AddCustomMeasurementSiteCommand(
                        telegram_user_id=message.from_user.id,
                        name=text,
                    ),
                )
                await message.answer(f"Точка «{result.name}» создана. Пришли обхват в сантиметрах, одно число.")
                return

            if field_name == "supplements_other":
                from fitness_bot.presentation.routers.profile import _SUPPLEMENT_DRAFT

                draft = _SUPPLEMENT_DRAFT.get(message.from_user.id) or {Supplement.OTHER.value}
                draft.add(Supplement.OTHER.value)
                draft.discard(Supplement.NONE.value)
                await mediator.send(
                    UpdateProfileCommand(
                        telegram_user_id=message.from_user.id,
                        field=ProfileField.SUPPLEMENTS,
                        value={"codes": sorted(draft), "other": text},
                    ),
                )
                _SUPPLEMENT_DRAFT.pop(message.from_user.id, None)
                if await finish_profile_edit_if_active(
                    message=message,
                    jinja_env=jinja_env,
                    mediator=mediator,
                    telegram_user_id=message.from_user.id,
                ):
                    return
                profile = await mediator.send(GetProfileQuery(telegram_user_id=message.from_user.id))
                if profile.profile_complete:
                    await show_info_offer(message=message, jinja_env=jinja_env)
                    return
                await show_next_onboarding_step(
                    message=message,
                    jinja_env=jinja_env,
                    mediator=mediator,
                    profile=profile,
                )
                return

            if field_name == ProfileField.WEIGHT.value:
                await mediator.send(
                    RecordWeightCommand(
                        telegram_user_id=message.from_user.id,
                        kilograms=text,
                        source=WeightSource.ONBOARDING,
                    ),
                )
                if await finish_profile_edit_if_active(
                    message=message,
                    jinja_env=jinja_env,
                    mediator=mediator,
                    telegram_user_id=message.from_user.id,
                ):
                    return
                profile = await mediator.send(GetProfileQuery(telegram_user_id=message.from_user.id))
                await show_next_onboarding_step(
                    message=message,
                    jinja_env=jinja_env,
                    mediator=mediator,
                    profile=profile,
                )
                return

            if field_name is None:
                await message.answer("Сейчас текст не ожидается.")
                return

            field = ProfileField(field_name)
            await mediator.send(
                UpdateProfileCommand(
                    telegram_user_id=message.from_user.id,
                    field=field,
                    value=text,
                ),
            )
            if await finish_profile_edit_if_active(
                message=message,
                jinja_env=jinja_env,
                mediator=mediator,
                telegram_user_id=message.from_user.id,
            ):
                return
            profile = await mediator.send(GetProfileQuery(telegram_user_id=message.from_user.id))
            if profile.profile_complete:
                await show_info_offer(message=message, jinja_env=jinja_env)
                return
            await show_next_onboarding_step(
                message=message,
                jinja_env=jinja_env,
                mediator=mediator,
                profile=profile,
            )
            return

        if workflow.expected_input == ExpectedInput.PROPOSAL_UTTERANCE:
            library_program_id = library_field_program_id(workflow.expected_field, LIBRARY_EDIT_FIELD_PREFIX)
            if library_program_id is not None:
                await handle_library_edit_utterance(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=message,
                    program_id=library_program_id,
                    text=text,
                )
            elif workflow.expected_field == "workout_edit":
                await handle_workout_edit_utterance(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=message,
                    text=text,
                )
            elif workflow.expected_field == "slot_actual":
                await handle_slot_actual_utterance(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=message,
                    text=text,
                )
            else:
                day_position = workflow.focus_slot if workflow.expected_field == "program_edit_day" else None
                await handle_proposal_utterance(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=message,
                    text=text,
                    day_position=day_position,
                )
            return

        if workflow.expected_input == ExpectedInput.COMPLETION_DEVIATION:
            await handle_completion_deviation_utterance(
                jinja_env=jinja_env,
                mediator=mediator,
                message=message,
                text=text,
            )
            return

        if workflow.expected_input == ExpectedInput.TECHNIQUE_VIDEO:
            await message.answer("Пришли видео упражнения (до 20 МБ), не текст.")
            return

        if workflow.expected_input == ExpectedInput.SLOT_WEIGHT:
            proposal_meta = parse_proposal_planned_field(workflow.expected_field)
            if proposal_meta is not None:
                day_position, _ = proposal_meta
                if workflow.focus_slot is None:
                    await message.answer("Сначала открой упражнение в черновике.")
                    return
                from fitness_bot.presentation.routers.session import _parse_weight_kg

                try:
                    weight_kg = _parse_weight_kg(text)
                except ValueError as exc:
                    await message.answer(f"{exc}. Напиши вес в кг или 0.")
                    return
                await ask_proposal_slot_load(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=message,
                    telegram_user_id=message.from_user.id,
                    day_position=day_position,
                    slot_position=workflow.focus_slot,
                    weight_kg=weight_kg,
                )
                return
            await handle_slot_weight_utterance(
                jinja_env=jinja_env,
                mediator=mediator,
                message=message,
                text=text,
                focus_slot=workflow.focus_slot,
            )
            return

        if workflow.expected_input == ExpectedInput.SLOT_LOAD:
            proposal_meta = parse_proposal_planned_field(workflow.expected_field)
            if proposal_meta is not None:
                day_position, weight_raw = proposal_meta
                if workflow.focus_slot is None:
                    await message.answer("Сначала открой упражнение в черновике.")
                    return
                pending = await mediator.send(GetPendingProposalQuery(telegram_user_id=message.from_user.id))
                slot = None
                if pending.document is not None:
                    day = next(
                        (item for item in pending.document.days if item.position == day_position),
                        None,
                    )
                    if day is not None:
                        slot = next(
                            (item for item in day.slots if item.position == workflow.focus_slot),
                            None,
                        )
                if slot is None:
                    await message.answer("Упражнение не найдено в черновике.")
                    return
                from fitness_bot.presentation.routers.session import _parse_positive_int

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
                await save_proposal_slot_planned(
                    jinja_env=jinja_env,
                    mediator=mediator,
                    message=message,
                    telegram_user_id=message.from_user.id,
                    day_position=day_position,
                    slot_position=workflow.focus_slot,
                    weight_kg=weight_raw or None,
                    reps=reps,
                    duration_seconds=duration_seconds,
                )
                return
            await handle_slot_load_utterance(
                mediator=mediator,
                message=message,
                text=text,
                focus_slot=workflow.focus_slot,
                draft_weight=workflow.expected_field,
            )
            return

        if workflow.expected_input == ExpectedInput.CODE_OR_LINK:
            from fitness_bot.presentation.routers.coach import _is_own_invite_code
            from fitness_bot.service.models.commands.catalog import ClaimProgramByCodeCommand
            from fitness_bot.service.models.commands.coach import AcceptCoachInviteCommand
            from fitness_bot.service.models.queries.coach import GetCoachCabinetQuery

            raw = text.strip()
            lowered = raw.casefold()
            if "start=" in lowered:
                raw = raw.split("start=", 1)[1].split("&", 1)[0].strip()
            if raw.casefold().startswith("join_"):
                raw = raw[5:]
            code = raw
            if code.startswith("c_") or code.startswith("C_"):
                invite_code = code[2:]
                cab = await mediator.send(GetCoachCabinetQuery(telegram_user_id=message.from_user.id))
                if _is_own_invite_code(raw_or_share=code, cabinet_invite_code=cab.invite_code):
                    await mediator.send(
                        ExpectInputCommand(
                            telegram_user_id=message.from_user.id,
                            expected_input=ExpectedInput.NONE,
                        ),
                    )
                    await message.answer("Это ваш код приглашения, отправьте его клиенту.")
                    return
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Продолжить — дать доступ",
                                callback_data=f"coach_accept:{invite_code}",
                            ),
                        ],
                        [InlineKeyboardButton(text="Отмена", callback_data="home")],
                    ],
                )
                await message.answer(
                    "Это код тренера. Он увидит прогресс, замеры и видео техники. Подключить?",
                    reply_markup=kb,
                )
                return
            if code.startswith("p_") or code.startswith("P_"):
                code = code[2:]
            try:
                claimed = await mediator.send(
                    ClaimProgramByCodeCommand(telegram_user_id=message.from_user.id, code=code),
                )
            except DomainError:
                # maybe coach code without prefix
                try:
                    await mediator.send(
                        AcceptCoachInviteCommand(telegram_user_id=message.from_user.id, code=code),
                    )
                    await message.answer("Тренер подключён.")
                    await mediator.send(
                        ExpectInputCommand(
                            telegram_user_id=message.from_user.id,
                            expected_input=ExpectedInput.NONE,
                        ),
                    )
                    return
                except DomainError as exc:
                    if "yourself" in str(exc):
                        await mediator.send(
                            ExpectInputCommand(
                                telegram_user_id=message.from_user.id,
                                expected_input=ExpectedInput.NONE,
                            ),
                        )
                        await message.answer("Это ваш код приглашения, отправьте его клиенту.")
                        return
                    await message.answer(f"Не распознали код: {exc}")
                    return
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=message.from_user.id,
                    expected_input=ExpectedInput.NONE,
                ),
            )
            note = "Уже в библиотеке." if claimed.already_claimed else "Шаблон в библиотеке."
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✨ Применить с адаптацией",
                            callback_data=f"lib_apply:{claimed.program_id}:adapt",
                        ),
                    ],
                    [InlineKeyboardButton(text="📚 Открыть карточку", callback_data=f"lib_card:{claimed.program_id}")],
                    [InlineKeyboardButton(text="Позже в библиотеке", callback_data="library")],
                ],
            )
            await message.answer(
                f"{note} «{claimed.title}». Автор вас не видит, пока не подключитесь.",
                reply_markup=kb,
            )
            return

        if workflow.expected_input == ExpectedInput.MODERATOR_REJECT_COMMENT:
            from uuid import UUID

            from fitness_bot.presentation.routers.moderator import apply_moderator_resolution_edits
            from fitness_bot.service.models.commands.coach import RejectCoachApplicationCommand

            app_id = UUID(workflow.expected_field or "")
            result = await mediator.send(
                RejectCoachApplicationCommand(
                    telegram_user_id=message.from_user.id,
                    application_id=app_id,
                    comment=text,
                ),
            )
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=message.from_user.id,
                    expected_input=ExpectedInput.NONE,
                ),
            )
            await apply_moderator_resolution_edits(bot=message.bot, result=result)
            msg = "Уже обработана." if result.already_processed else "Заявка отклонена."
            await message.answer(msg)
            return

        if workflow.expected_input == ExpectedInput.COACH_EDIT_CLIENT:
            from uuid import UUID

            from fitness_bot.presentation.keyboards import coach_client_proposal_keyboard
            from fitness_bot.presentation.routers.program import _can_approve_program, render_proposal
            from fitness_bot.service.models.commands.program import ProposeProgramChangeCommand

            client_id = UUID(workflow.expected_field or "")
            try:
                result = await mediator.send(
                    ProposeProgramChangeCommand(
                        telegram_user_id=message.from_user.id,
                        utterance=text,
                        subject_user_id=client_id,
                    ),
                )
            except DomainError as exc:
                await message.answer(str(exc))
                return
            if result.agent_unavailable:
                await message.answer("Агент временно недоступен.")
                return
            if result.schema_failed or result.document is None:
                await message.answer(
                    "Не удалось разобрать правку. Попробуйте ещё раз.",
                    reply_markup=coach_client_proposal_keyboard(
                        client_user_id=str(client_id),
                        can_approve=False,
                    ),
                )
                return
            can_approve = _can_approve_program(result.document)
            await render_proposal(
                jinja_env=jinja_env,
                mediator=mediator,
                message=message,
                reply=result.reply,
                document=result.document,
                telegram_user_id=message.from_user.id,
                reply_markup=coach_client_proposal_keyboard(
                    client_user_id=str(client_id),
                    can_approve=can_approve,
                ),
            )
            return

        if workflow.expected_input == ExpectedInput.COACH_APPLICATION:
            field = workflow.expected_field or "1:name_bio"
            if field.startswith("2:"):
                payload = field[2:]
                name, _, bio = payload.partition("|")
                await mediator.send(
                    ExpectInputCommand(
                        telegram_user_id=message.from_user.id,
                        expected_input=ExpectedInput.COACH_CREDENTIAL,
                        expected_field=f"{name}|{bio}|{text.strip()}",
                    ),
                )
                await message.answer(
                    "Заявка 3/3: пришлите фото подтверждения (именно фото, не файл).",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="home")]],
                    ),
                )
                return
            lines = text.splitlines()
            name = lines[0].strip()
            bio = "\n".join(lines[1:]).strip() or name
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=message.from_user.id,
                    expected_input=ExpectedInput.COACH_APPLICATION,
                    expected_field=f"2:{name}|{bio}",
                ),
            )
            await message.answer(
                "Заявка 2/3: пришлите URL портфолио.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="home")]],
                ),
            )
            return

        if (
            workflow.expected_input == ExpectedInput.PROFILE_FIELD
            and workflow.expected_field == "moderator_grant_telegram_id"
        ):
            from fitness_bot.service.models.commands.coach import GrantModeratorCommand

            target_id = int(text.strip())
            await mediator.send(
                GrantModeratorCommand(
                    actor_telegram_user_id=message.from_user.id,
                    target_telegram_user_id=target_id,
                ),
            )
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=message.from_user.id,
                    expected_input=ExpectedInput.NONE,
                ),
            )
            await message.answer("Модератор добавлен.")
            return

        await message.answer("Сейчас этот ввод не подходит. Открой нужный раздел через меню.")
    except (DomainError, ValueError) as exc:
        await message.answer(f"Не получилось сохранить: {exc}")


def create_text_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="text")

    @router.message(F.text, ~F.text.startswith("/"))
    async def handle_tg_text(message: Message) -> None:
        assert message.text is not None
        await handle_user_utterance(
            message=message,
            text=message.text,
            jinja_env=jinja_env,
            mediator=mediator,
        )

    return router
