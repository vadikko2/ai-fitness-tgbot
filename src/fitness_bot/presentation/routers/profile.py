from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.enums import (
    ActivityLevel,
    ExpectedInput,
    ExperienceLevel,
    Goal,
    ProfileField,
    Sex,
    Supplement,
    TrainingPlace,
)
from fitness_bot.domain.users.user import local_calendar_date
from fitness_bot.presentation.flow_helpers import (
    begin_profile_edit,
    clear_profile_edit,
    finish_profile_edit_if_active,
    home_keyboard_from,
    markup_for_profile_field,
    profile_text,
    render_home_text,
    show_info_offer,
    show_next_onboarding_step,
)
from fitness_bot.presentation.keyboards import (
    activity_level_keyboard,
    body_fat_unknown_keyboard,
    diet_prefs_none_keyboard,
    experience_keyboard,
    goal_keyboard,
    nutrition_constraints_none_keyboard,
    pharma_keyboard,
    profile_edit_keyboard,
    profile_hub_keyboard,
    profile_reminders_keyboard,
    session_minutes_keyboard,
    sex_keyboard,
    supplements_keyboard,
    training_place_keyboard,
    weekdays_keyboard,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand, SetGoalCommand, UpdateProfileCommand
from fitness_bot.service.models.queries.body import GetMeasurementHistoryQuery, GetWeightHistoryQuery
from fitness_bot.service.models.queries.training_reminder import GetTrainingReminderSettingsQuery
from fitness_bot.service.models.queries.users import GetHomeQuery, GetProfileQuery

# Temporary selected weekdays while user toggles before "Готово".
_WEEKDAY_DRAFT: dict[int, set[int]] = {}
_SUPPLEMENT_DRAFT: dict[int, set[str]] = {}


async def profile_hub_text(*, jinja_env: Environment, mediator: RequestMediator, telegram_user_id: int) -> str:
    profile = await mediator.send(GetProfileQuery(telegram_user_id=telegram_user_id))
    weights = await mediator.send(GetWeightHistoryQuery(telegram_user_id=telegram_user_id, limit=1))
    measurements = await mediator.send(GetMeasurementHistoryQuery(telegram_user_id=telegram_user_id, limit=1))
    last_weight = weights.items[0] if weights.items else None
    last_measurement = measurements.entries[0] if measurements.entries else None
    return jinja_env.get_template("profile_hub.j2").render(
        profile_text=profile_text(jinja_env=jinja_env, profile=profile),
        last_weight_kg=last_weight.kilograms if last_weight else None,
        last_weight_on=last_weight.measured_on if last_weight else None,
        last_measurement_on=(
            local_calendar_date(now=last_measurement.measured_at, timezone_offset=profile.timezone_offset)
            if last_measurement
            else None
        ),
    )


def create_profile_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="profile")

    async def _answer(callback: CallbackQuery, text: str, **kwargs) -> None:
        if callback.message:
            await callback.message.answer(text, reply_markup=kwargs.get("reply_markup"))
        await callback.answer()

    async def _continue_onboarding(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert isinstance(callback.message, Message)
        if await finish_profile_edit_if_active(
            message=callback.message,
            jinja_env=jinja_env,
            mediator=mediator,
            telegram_user_id=callback.from_user.id,
        ):
            await callback.answer()
            return
        profile = await mediator.send(GetProfileQuery(telegram_user_id=callback.from_user.id))
        await show_next_onboarding_step(
            message=callback.message,
            jinja_env=jinja_env,
            mediator=mediator,
            profile=profile,
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("onb_sex:"))
    async def handle_onb_sex(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        sex = Sex(callback.data.split(":", 1)[1])
        await mediator.send(
            UpdateProfileCommand(
                telegram_user_id=callback.from_user.id,
                field=ProfileField.SEX,
                value=sex.value,
            ),
        )
        await _continue_onboarding(callback)

    @router.callback_query(F.data.startswith("onb_exp:"))
    async def handle_onb_exp(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        level = ExperienceLevel(callback.data.split(":", 1)[1])
        await mediator.send(
            UpdateProfileCommand(
                telegram_user_id=callback.from_user.id,
                field=ProfileField.EXPERIENCE,
                value=level.value,
            ),
        )
        await _continue_onboarding(callback)

    @router.callback_query(F.data.startswith("onb_place:"))
    async def handle_onb_place(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        place = TrainingPlace(callback.data.split(":", 1)[1])
        await mediator.send(
            UpdateProfileCommand(
                telegram_user_id=callback.from_user.id,
                field=ProfileField.TRAINING_PLACE,
                value=place.value,
            ),
        )
        await _continue_onboarding(callback)

    @router.callback_query(F.data.startswith("onb_act:"))
    async def handle_onb_act(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        level = ActivityLevel(callback.data.split(":", 1)[1])
        await mediator.send(
            UpdateProfileCommand(
                telegram_user_id=callback.from_user.id,
                field=ProfileField.ACTIVITY_LEVEL,
                value=level.value,
            ),
        )
        await _continue_onboarding(callback)

    @router.callback_query(F.data.startswith("onb_mins:"))
    async def handle_onb_mins(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        minutes = int(callback.data.split(":", 1)[1])
        await mediator.send(
            UpdateProfileCommand(
                telegram_user_id=callback.from_user.id,
                field=ProfileField.SESSION_MINUTES,
                value=minutes,
            ),
        )
        await _continue_onboarding(callback)

    @router.callback_query(F.data.startswith("onb_bf:"))
    async def handle_onb_bf(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        payload = callback.data.split(":", 1)[1]
        if payload != "unknown":
            await callback.answer()
            return
        await mediator.send(
            UpdateProfileCommand(
                telegram_user_id=callback.from_user.id,
                field=ProfileField.BODY_FAT,
                value="unknown",
            ),
        )
        await _continue_onboarding(callback)

    @router.callback_query(F.data.startswith("onb_supp:"))
    async def handle_onb_supp(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        payload = callback.data.split(":", 1)[1]
        profile = await mediator.send(GetProfileQuery(telegram_user_id=callback.from_user.id))
        draft = _SUPPLEMENT_DRAFT.setdefault(
            callback.from_user.id,
            set(profile.supplements or ()),
        )
        if payload == "done":
            if not draft:
                await callback.answer("Выбери хотя бы один пункт")
                return
            if Supplement.OTHER.value in draft:
                await mediator.send(
                    ExpectInputCommand(
                        telegram_user_id=callback.from_user.id,
                        expected_input=ExpectedInput.PROFILE_FIELD,
                        expected_field="supplements_other",
                    ),
                )
                text = jinja_env.get_template("onboarding_prompt.j2").render(field="supplements_other")
                await _answer(callback, text)
                return
            await mediator.send(
                UpdateProfileCommand(
                    telegram_user_id=callback.from_user.id,
                    field=ProfileField.SUPPLEMENTS,
                    value=sorted(draft),
                ),
            )
            _SUPPLEMENT_DRAFT.pop(callback.from_user.id, None)
            await _continue_onboarding(callback)
            return

        code = Supplement(payload)
        if code == Supplement.NONE:
            draft.clear()
            draft.add(Supplement.NONE.value)
        else:
            draft.discard(Supplement.NONE.value)
            if code.value in draft:
                draft.remove(code.value)
            else:
                draft.add(code.value)
        assert isinstance(callback.message, Message)
        text = jinja_env.get_template("onboarding_prompt.j2").render(field="supplements")
        await callback.message.edit_text(text, reply_markup=supplements_keyboard(draft))
        await callback.answer()

    @router.callback_query(F.data.startswith("onb_diet:"))
    async def handle_onb_diet(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        if callback.data.split(":", 1)[1] != "none":
            await callback.answer()
            return
        await mediator.send(
            UpdateProfileCommand(
                telegram_user_id=callback.from_user.id,
                field=ProfileField.DIET_PREFS,
                value="",
            ),
        )
        await _continue_onboarding(callback)

    @router.callback_query(F.data.startswith("onb_nconst:"))
    async def handle_onb_nconst(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        if callback.data.split(":", 1)[1] != "none":
            await callback.answer()
            return
        await mediator.send(
            UpdateProfileCommand(
                telegram_user_id=callback.from_user.id,
                field=ProfileField.NUTRITION_CONSTRAINTS,
                value="",
            ),
        )
        await _continue_onboarding(callback)

    @router.callback_query(F.data.startswith("onb_days:"))
    async def handle_onb_days(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        payload = callback.data.split(":", 1)[1]
        profile = await mediator.send(GetProfileQuery(telegram_user_id=callback.from_user.id))
        draft = _WEEKDAY_DRAFT.setdefault(callback.from_user.id, set(profile.training_weekdays))
        if payload == "done":
            await mediator.send(
                UpdateProfileCommand(
                    telegram_user_id=callback.from_user.id,
                    field=ProfileField.TRAINING_WEEKDAYS,
                    value=sorted(draft),
                ),
            )
            _WEEKDAY_DRAFT.pop(callback.from_user.id, None)
            await _continue_onboarding(callback)
            return
        day = int(payload)
        if day in draft:
            draft.remove(day)
        else:
            draft.add(day)
        assert profile.days_per_week is not None
        assert isinstance(callback.message, Message)
        text = jinja_env.get_template("onboarding_prompt.j2").render(
            field="training_weekdays",
            days_per_week=profile.days_per_week,
        )
        await callback.message.edit_text(
            text,
            reply_markup=weekdays_keyboard(draft, days_needed=profile.days_per_week),
        )
        await callback.answer()

    @router.callback_query(F.data == "onb_limits:none")
    async def handle_onb_limits_none(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await mediator.send(
            UpdateProfileCommand(
                telegram_user_id=callback.from_user.id,
                field=ProfileField.LIMITATIONS,
                value="",
            ),
        )
        await _continue_onboarding(callback)

    @router.callback_query(F.data.startswith("onb_goal:"))
    async def handle_onb_goal(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        goal = Goal(callback.data.split(":", 1)[1])
        await mediator.send(SetGoalCommand(telegram_user_id=callback.from_user.id, goal=goal))
        assert isinstance(callback.message, Message)
        await show_info_offer(message=callback.message, jinja_env=jinja_env)
        await callback.answer()

    @router.callback_query(F.data == "home")
    async def handle_home(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        clear_profile_edit(callback.from_user.id)
        # Leave any pending utterance flow so menu navigation is not stuck in draft edit mode.
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.NONE,
            ),
        )
        home = await mediator.send(GetHomeQuery(telegram_user_id=callback.from_user.id))
        text = render_home_text(jinja_env=jinja_env, home=home)
        await _answer(callback, text, reply_markup=home_keyboard_from(home))

    @router.callback_query(F.data == "profile")
    async def handle_profile(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        clear_profile_edit(callback.from_user.id)
        await mediator.send(
            ExpectInputCommand(telegram_user_id=callback.from_user.id, expected_input=ExpectedInput.NONE),
        )
        text = await profile_hub_text(jinja_env=jinja_env, mediator=mediator, telegram_user_id=callback.from_user.id)
        await _answer(callback, text, reply_markup=profile_hub_keyboard())

    @router.callback_query(F.data == "prof_form")
    async def handle_prof_form(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        clear_profile_edit(callback.from_user.id)
        profile = await mediator.send(GetProfileQuery(telegram_user_id=callback.from_user.id))
        text = profile_text(jinja_env=jinja_env, profile=profile)
        await _answer(callback, text, reply_markup=profile_edit_keyboard())

    @router.callback_query(F.data == "prof_remind")
    async def handle_prof_remind(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        settings = await mediator.send(GetTrainingReminderSettingsQuery(telegram_user_id=callback.from_user.id))
        await _answer(
            callback,
            jinja_env.get_template("training_reminder_settings.j2").render(),
            reply_markup=profile_reminders_keyboard(
                evening_enabled=settings.evening_enabled,
                morning_enabled=settings.morning_enabled,
            ),
        )

    @router.callback_query(F.data.startswith("prof_pharma:"))
    async def handle_prof_pharma(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        action = callback.data.split(":", 1)[1]
        if action == "none":
            begin_profile_edit(callback.from_user.id)
            await mediator.send(
                UpdateProfileCommand(
                    telegram_user_id=callback.from_user.id,
                    field=ProfileField.PHARMA,
                    value="",
                ),
            )
            assert isinstance(callback.message, Message)
            await finish_profile_edit_if_active(
                message=callback.message,
                jinja_env=jinja_env,
                mediator=mediator,
                telegram_user_id=callback.from_user.id,
            )
            await callback.answer()
            return
        if action == "text":
            begin_profile_edit(callback.from_user.id)
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=callback.from_user.id,
                    expected_input=ExpectedInput.PROFILE_FIELD,
                    expected_field=ProfileField.PHARMA.value,
                ),
            )
            text = jinja_env.get_template("onboarding_prompt.j2").render(field="pharma")
            await _answer(callback, text)
            return
        await callback.answer()

    @router.callback_query(F.data.startswith("prof_edit:"))
    async def handle_prof_edit(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        begin_profile_edit(callback.from_user.id)
        field_name = callback.data.split(":", 1)[1]
        if field_name == "goal":
            await _answer(callback, "Выбери новую цель.", reply_markup=goal_keyboard(prefix="prof_goal"))
            return
        if field_name == "sex":
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=callback.from_user.id,
                    expected_input=ExpectedInput.PROFILE_FIELD,
                    expected_field=ProfileField.SEX.value,
                ),
            )
            await _answer(callback, "Укажи пол.", reply_markup=sex_keyboard())
            return
        if field_name == ProfileField.PHARMA.value:
            text = jinja_env.get_template("onboarding_prompt.j2").render(field="pharma")
            await _answer(callback, text, reply_markup=pharma_keyboard())
            return
        field = ProfileField(field_name)
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.PROFILE_FIELD,
                expected_field=field.value,
            ),
        )
        profile = await mediator.send(GetProfileQuery(telegram_user_id=callback.from_user.id))
        text = jinja_env.get_template("onboarding_prompt.j2").render(
            field=field.value,
            days_per_week=profile.days_per_week,
        )
        markup = None
        if field == ProfileField.TRAINING_WEEKDAYS and profile.days_per_week is not None:
            _WEEKDAY_DRAFT[callback.from_user.id] = set(profile.training_weekdays)
            markup = weekdays_keyboard(set(profile.training_weekdays), days_needed=profile.days_per_week)
        elif field == ProfileField.EXPERIENCE:
            markup = experience_keyboard()
        elif field == ProfileField.TRAINING_PLACE:
            markup = training_place_keyboard()
        elif field == ProfileField.ACTIVITY_LEVEL:
            markup = activity_level_keyboard()
        elif field == ProfileField.SESSION_MINUTES:
            markup = session_minutes_keyboard()
        elif field == ProfileField.BODY_FAT:
            markup = body_fat_unknown_keyboard()
        elif field == ProfileField.SUPPLEMENTS:
            _SUPPLEMENT_DRAFT[callback.from_user.id] = set(profile.supplements or ())
            markup = supplements_keyboard(set(profile.supplements or ()))
        elif field == ProfileField.DIET_PREFS:
            markup = diet_prefs_none_keyboard()
        elif field == ProfileField.NUTRITION_CONSTRAINTS:
            markup = nutrition_constraints_none_keyboard()
        elif field == ProfileField.LIMITATIONS:
            from fitness_bot.presentation.keyboards import limitations_none_keyboard

            markup = limitations_none_keyboard()
        elif field == ProfileField.EXPERIENCE_DETAILS:
            markup = None
        else:
            markup = markup_for_profile_field(field, days_per_week=profile.days_per_week)
        await _answer(callback, text, reply_markup=markup)

    @router.callback_query(F.data.startswith("prof_goal:"))
    async def handle_prof_goal(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        clear_profile_edit(callback.from_user.id)
        goal = Goal(callback.data.split(":", 1)[1])
        await mediator.send(SetGoalCommand(telegram_user_id=callback.from_user.id, goal=goal))
        assert isinstance(callback.message, Message)
        profile = await mediator.send(GetProfileQuery(telegram_user_id=callback.from_user.id))
        text = profile_text(jinja_env=jinja_env, profile=profile)
        await _answer(callback, text, reply_markup=profile_edit_keyboard())

    return router
