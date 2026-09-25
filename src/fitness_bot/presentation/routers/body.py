from __future__ import annotations

import logging
from datetime import time
from uuid import UUID

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.body.reminder import DEFAULT_WEIGHT_REMINDER_TIME, DEFAULT_WEIGHT_REMINDER_WEEKDAYS
from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.presentation.flow_helpers import weekdays_label
from fitness_bot.presentation.keyboards import (
    back_to_menu_keyboard,
    measurement_sites_keyboard,
    weight_menu_keyboard,
    weight_reminder_menu_keyboard,
    weight_reminder_time_keyboard,
    weight_reminder_weekdays_keyboard,
)
from fitness_bot.presentation.measurement_guide_images import (
    caption_fits_telegram,
    measurement_guide_image_path,
    measurement_overview_image_path,
)
from fitness_bot.service.models.commands.body import (
    EnsureDefaultWeightReminderCommand,
    EnsureFixedMeasurementSitesCommand,
    SetWeightReminderCommand,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.body import (
    GetMeasurementGuideQuery,
    GetMeasurementHistoryQuery,
    GetWeightHistoryQuery,
    GetWeightReminderQuery,
)
from fitness_bot.service.models.queries.users import GetProfileQuery

logger = logging.getLogger(__name__)

# Temporary selected weekdays while user toggles before "Готово".
_REMINDER_WEEKDAY_DRAFT: dict[int, set[int]] = {}


def _format_local_time(value: time) -> str:
    return value.strftime("%H:%M")


async def _current_reminder(
    *,
    mediator: RequestMediator,
    telegram_user_id: int,
) -> tuple[list[int], time]:
    await mediator.send(EnsureDefaultWeightReminderCommand(telegram_user_id=telegram_user_id))
    reminder = await mediator.send(GetWeightReminderQuery(telegram_user_id=telegram_user_id))
    weekdays = reminder.weekdays or sorted(DEFAULT_WEIGHT_REMINDER_WEEKDAYS)
    local_time = reminder.local_time or DEFAULT_WEIGHT_REMINDER_TIME
    return weekdays, local_time


def create_body_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="body")

    async def _answer(callback: CallbackQuery, text: str, **kwargs) -> None:
        if callback.message:
            await callback.message.answer(text, reply_markup=kwargs.get("reply_markup"))
        await callback.answer()

    async def _show_reminder_menu(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        weekdays, local_time = await _current_reminder(
            mediator=mediator,
            telegram_user_id=callback.from_user.id,
        )
        text = jinja_env.get_template("weight_reminder.j2").render(
            weekdays_label=weekdays_label(weekdays),
            local_time=_format_local_time(local_time),
        )
        await _answer(callback, text, reply_markup=weight_reminder_menu_keyboard())

    @router.callback_query(F.data == "wt_menu")
    async def handle_wt_menu(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        history = await mediator.send(GetWeightHistoryQuery(telegram_user_id=callback.from_user.id, limit=1))
        weekdays, local_time = await _current_reminder(
            mediator=mediator,
            telegram_user_id=callback.from_user.id,
        )
        text = jinja_env.get_template("weight.j2").render(
            latest_kg=history.latest_kg,
            reminder_weekdays_label=weekdays_label(weekdays),
            reminder_time=_format_local_time(local_time),
        )
        await _answer(callback, text, reply_markup=weight_menu_keyboard())

    @router.callback_query(F.data == "wt_log")
    async def handle_wt_log(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.WEIGHT,
            ),
        )
        text = jinja_env.get_template("weight_prompt.j2").render()
        await _answer(callback, text)

    @router.callback_query(F.data == "feel")
    async def handle_feel(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.WELLBEING,
            ),
        )
        text = jinja_env.get_template("onboarding_prompt.j2").render(field="wellbeing")
        await _answer(callback, text)

    @router.callback_query(F.data == "wt_hist")
    async def handle_wt_hist(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        history = await mediator.send(GetWeightHistoryQuery(telegram_user_id=callback.from_user.id))
        text = jinja_env.get_template("weight_history.j2").render(items=history.items)
        await _answer(callback, text, reply_markup=back_to_menu_keyboard())

    @router.callback_query(F.data == "wt_remind")
    async def handle_wt_remind(callback: CallbackQuery) -> None:
        await _show_reminder_menu(callback)

    @router.callback_query(F.data.startswith("wt_rm_preset:"))
    async def handle_wt_rm_preset(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        preset = callback.data.split(":", 1)[1]
        _, local_time = await _current_reminder(mediator=mediator, telegram_user_id=callback.from_user.id)
        if preset == "weekly":
            weekdays = sorted(DEFAULT_WEIGHT_REMINDER_WEEKDAYS)
        elif preset == "daily":
            weekdays = list(range(1, 8))
        else:
            await callback.answer()
            return
        await mediator.send(
            SetWeightReminderCommand(
                telegram_user_id=callback.from_user.id,
                local_time=local_time,
                weekdays=weekdays,
            ),
        )
        await _show_reminder_menu(callback)

    @router.callback_query(F.data == "wt_rm_custom")
    async def handle_wt_rm_custom(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        weekdays, _ = await _current_reminder(mediator=mediator, telegram_user_id=callback.from_user.id)
        draft = set(weekdays)
        _REMINDER_WEEKDAY_DRAFT[callback.from_user.id] = draft
        text = jinja_env.get_template("weight_reminder_days.j2").render()
        await _answer(callback, text, reply_markup=weight_reminder_weekdays_keyboard(draft))

    @router.callback_query(F.data.startswith("wt_rm_day:"))
    async def handle_wt_rm_day(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        payload = callback.data.split(":", 1)[1]
        weekdays, local_time = await _current_reminder(
            mediator=mediator,
            telegram_user_id=callback.from_user.id,
        )
        draft = _REMINDER_WEEKDAY_DRAFT.setdefault(callback.from_user.id, set(weekdays))
        if payload == "done":
            if not draft:
                await callback.answer("Выбери хотя бы один день", show_alert=True)
                return
            await mediator.send(
                SetWeightReminderCommand(
                    telegram_user_id=callback.from_user.id,
                    local_time=local_time,
                    weekdays=sorted(draft),
                ),
            )
            _REMINDER_WEEKDAY_DRAFT.pop(callback.from_user.id, None)
            await _show_reminder_menu(callback)
            return
        day = int(payload)
        if day in draft:
            draft.remove(day)
        else:
            draft.add(day)
        assert isinstance(callback.message, Message)
        text = jinja_env.get_template("weight_reminder_days.j2").render()
        await callback.message.edit_text(text, reply_markup=weight_reminder_weekdays_keyboard(draft))
        await callback.answer()

    @router.callback_query(F.data == "wt_rm_time")
    async def handle_wt_rm_time(callback: CallbackQuery) -> None:
        text = jinja_env.get_template("weight_reminder_time.j2").render()
        await _answer(callback, text, reply_markup=weight_reminder_time_keyboard())

    @router.callback_query(F.data.startswith("wt_rm_at:"))
    async def handle_wt_rm_at(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        payload = callback.data.split(":", 1)[1]
        weekdays, _ = await _current_reminder(mediator=mediator, telegram_user_id=callback.from_user.id)
        if payload == "custom":
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=callback.from_user.id,
                    expected_input=ExpectedInput.PROFILE_FIELD,
                    expected_field="weight_reminder_time",
                ),
            )
            text = jinja_env.get_template("weight_reminder_prompt.j2").render()
            await _answer(callback, text)
            return
        hour_s, minute_s = payload.split(":")
        local_time = time(hour=int(hour_s), minute=int(minute_s))
        await mediator.send(
            SetWeightReminderCommand(
                telegram_user_id=callback.from_user.id,
                local_time=local_time,
                weekdays=weekdays,
            ),
        )
        await _show_reminder_menu(callback)

    @router.callback_query(F.data == "meas_menu")
    async def handle_meas_menu(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await mediator.send(EnsureFixedMeasurementSitesCommand())
        history = await mediator.send(GetMeasurementHistoryQuery(telegram_user_id=callback.from_user.id))
        sites = [(str(site.id), site.name) for site in history.sites]
        text = jinja_env.get_template("measurement.j2").render()
        profile = await mediator.send(GetProfileQuery(telegram_user_id=callback.from_user.id))
        overview = measurement_overview_image_path(sex=profile.sex)
        markup = measurement_sites_keyboard(sites)
        if overview is not None and callback.message is not None:
            try:
                photo = FSInputFile(path=str(overview))
                if caption_fits_telegram(text):
                    if callback.message:
                        await callback.message.answer_photo(photo, caption=text, reply_markup=markup)
                    await callback.answer()
                else:
                    # Caption too long: keep a single text screen (guide copy > photo).
                    await _answer(callback, text, reply_markup=markup)
                return
            except Exception:
                logger.exception("failed to send measurement overview photo path=%s", overview)
        await _answer(callback, text, reply_markup=markup)

    @router.callback_query(F.data.startswith("meas_site:"))
    async def handle_meas_site(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        site_id = UUID(callback.data.split(":", 1)[1])
        guide = await mediator.send(GetMeasurementGuideQuery(site_id=site_id))
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.MEASUREMENT_VALUE,
                pending_site_id=site_id,
            ),
        )
        text = jinja_env.get_template("measurement_guide.j2").render(
            site_name=guide.site_name,
            instruction=guide.instruction,
        )
        profile = await mediator.send(GetProfileQuery(telegram_user_id=callback.from_user.id))
        image_path = measurement_guide_image_path(guide.site_code, sex=profile.sex)
        if image_path is not None and callback.message is not None:
            try:
                photo = FSInputFile(path=str(image_path))
                if caption_fits_telegram(text):
                    if callback.message:
                        await callback.message.answer_photo(photo, caption=text)
                    await callback.answer()
                else:
                    await _answer(callback, text)
                return
            except Exception:
                logger.exception(
                    "failed to send measurement guide photo site=%s path=%s",
                    guide.site_code,
                    image_path,
                )
        elif image_path is None and guide.site_code:
            logger.warning(
                "measurement guide image missing for site_code=%s sex=%s",
                guide.site_code,
                profile.sex,
            )
        await _answer(callback, text)

    @router.callback_query(F.data == "meas_custom")
    async def handle_meas_custom(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await mediator.send(
            ExpectInputCommand(
                telegram_user_id=callback.from_user.id,
                expected_input=ExpectedInput.PROFILE_FIELD,
                expected_field="custom_measurement_name",
            ),
        )
        text = jinja_env.get_template("onboarding_prompt.j2").render(
            field="custom_measurement_name",
            days_per_week=None,
        )
        await _answer(callback, text)

    @router.callback_query(F.data.startswith("meas_hist:"))
    async def handle_meas_hist(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        site_id = UUID(callback.data.split(":", 1)[1])
        history = await mediator.send(
            GetMeasurementHistoryQuery(telegram_user_id=callback.from_user.id, site_id=site_id),
        )
        site_name = next((site.name for site in history.sites if site.id == site_id), None)
        text = jinja_env.get_template("history.j2").render(entries=history.entries, site_name=site_name)
        await _answer(callback, text, reply_markup=back_to_menu_keyboard())

    return router


def parse_reminder_time(text: str) -> time:
    parts = text.strip().split(":")
    if len(parts) != 2:
        raise ValueError("expected HH:MM")
    return time(hour=int(parts[0]), minute=int(parts[1]))


async def apply_weight_reminder_time(*, mediator: RequestMediator, telegram_user_id: int, text: str) -> None:
    local_time = parse_reminder_time(text)
    weekdays, _ = await _current_reminder(mediator=mediator, telegram_user_id=telegram_user_id)
    await mediator.send(
        SetWeightReminderCommand(
            telegram_user_id=telegram_user_id,
            local_time=local_time,
            weekdays=weekdays,
        ),
    )
