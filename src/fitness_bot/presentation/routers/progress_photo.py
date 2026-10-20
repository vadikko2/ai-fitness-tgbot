from __future__ import annotations

import logging
from datetime import time
from uuid import UUID

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InputMediaPhoto,
    Message,
)
from cqrs import RequestMediator
from jinja2 import Environment

from fitness_bot.domain.body.reminder import (
    DEFAULT_PROGRESS_PHOTO_REMINDER_TIME,
    DEFAULT_PROGRESS_PHOTO_REMINDER_WEEKDAYS,
)
from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.domain.errors import DomainError
from fitness_bot.presentation.flow_helpers import weekdays_label
from fitness_bot.presentation.keyboards import (
    progress_photo_history_keyboard,
    progress_photo_menu_keyboard,
    progress_photo_reminder_menu_keyboard,
    progress_photo_reminder_time_keyboard,
    progress_photo_reminder_weekdays_keyboard,
)
from fitness_bot.presentation.progress_pose_images import (
    caption_fits_telegram,
    progress_pose_image_path,
    progress_pose_overview_image_path,
)
from fitness_bot.presentation.routers.body import parse_reminder_time
from fitness_bot.service.models.commands.body import (
    CancelProgressPhotoCaptureCommand,
    EnsureDefaultProgressPhotoReminderCommand,
    RememberProgressPhotoFileIdCommand,
    SetProgressPhotoReminderCommand,
    StartProgressPhotoCaptureCommand,
)
from fitness_bot.service.models.commands.users import ExpectInputCommand
from fitness_bot.service.models.queries.body import (
    GetProgressPhotoHistoryQuery,
    GetProgressPhotoReminderQuery,
    GetProgressPhotoSetQuery,
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
    await mediator.send(EnsureDefaultProgressPhotoReminderCommand(telegram_user_id=telegram_user_id))
    reminder = await mediator.send(GetProgressPhotoReminderQuery(telegram_user_id=telegram_user_id))
    weekdays = reminder.weekdays or sorted(DEFAULT_PROGRESS_PHOTO_REMINDER_WEEKDAYS)
    local_time = reminder.local_time or DEFAULT_PROGRESS_PHOTO_REMINDER_TIME
    return weekdays, local_time


async def send_angle_prompt(
    *,
    jinja_env: Environment,
    mediator: RequestMediator,
    telegram_user_id: int,
    angle: str,
    message: Message | None = None,
    bot=None,
    chat_id: int | None = None,
    reply_markup=None,
) -> None:
    text = jinja_env.get_template("progress_photo_angle.j2").render(angle=angle)
    profile = await mediator.send(GetProfileQuery(telegram_user_id=telegram_user_id))
    image_path = progress_pose_image_path(angle, sex=profile.sex)

    async def _send_text() -> None:
        if message is not None:
            await message.answer(text, reply_markup=reply_markup)
        elif bot is not None and chat_id is not None:
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

    async def _send_photo(photo: FSInputFile) -> None:
        if message is not None:
            await message.answer_photo(photo, caption=text, reply_markup=reply_markup)
        elif bot is not None and chat_id is not None:
            await bot.send_photo(chat_id=chat_id, photo=photo, caption=text, reply_markup=reply_markup)

    if image_path is not None:
        try:
            photo = FSInputFile(path=str(image_path))
            if caption_fits_telegram(text):
                await _send_photo(photo)
                return
        except Exception:
            logger.exception("failed to send progress pose guide path=%s", image_path)
    await _send_text()


async def send_progress_photo_set(
    *,
    message: Message,
    mediator: RequestMediator,
    jinja_env: Environment,
    telegram_user_id: int,
    set_id: UUID,
    subject_user_id: UUID | None = None,
) -> None:
    delivery = await mediator.send(
        GetProgressPhotoSetQuery(
            telegram_user_id=telegram_user_id,
            set_id=set_id,
            subject_user_id=subject_user_id,
        ),
    )
    # Owner view when query result has no subject; coach views resolve owner via set id.
    is_owner_view = delivery.subject_user_id is None
    caption = jinja_env.get_template("progress_photo_set_caption.j2").render(
        local_date=delivery.local_date.strftime("%d.%m.%Y"),
    )
    media: list[InputMediaPhoto] = []
    remember: list[tuple[UUID, int]] = []  # (photo_id, media index)
    for photo in delivery.photos:
        if photo.missing or photo.photo_id is None:
            continue
        is_first = not media
        if photo.telegram_file_id:
            media.append(
                InputMediaPhoto(
                    media=photo.telegram_file_id,
                    caption=caption if is_first else None,
                    has_spoiler=True,
                ),
            )
        elif photo.body is not None:
            media.append(
                InputMediaPhoto(
                    media=BufferedInputFile(photo.body, filename=f"{photo.angle.value}.jpg"),
                    caption=caption if is_first else None,
                    has_spoiler=True,
                ),
            )
            if is_owner_view:
                remember.append((photo.photo_id, len(media) - 1))
        else:
            continue

    if not media:
        await message.answer("Фото этого сета недоступны.")
        return

    sent = await message.answer_media_group(media)
    if is_owner_view:
        for photo_id, media_index in remember:
            if media_index >= len(sent):
                continue
            msg = sent[media_index]
            if not msg.photo:
                continue
            await mediator.send(
                RememberProgressPhotoFileIdCommand(
                    telegram_user_id=telegram_user_id,
                    set_id=set_id,
                    photo_id=photo_id,
                    telegram_file_id=msg.photo[-1].file_id,
                ),
            )


async def show_progress_photo_history(
    *,
    callback: CallbackQuery,
    jinja_env: Environment,
    mediator: RequestMediator,
    telegram_user_id: int,
    offset: int = 0,
    subject_user_id: UUID | None = None,
    back_callback: str = "pp_menu",
) -> None:
    history = await mediator.send(
        GetProgressPhotoHistoryQuery(
            telegram_user_id=telegram_user_id,
            subject_user_id=subject_user_id,
            offset=offset,
            limit=10,
        ),
    )
    text = jinja_env.get_template("progress_photo_history.j2").render(items=history.items)
    markup = progress_photo_history_keyboard(
        items=[(str(item.set_id), f"📅 {item.local_date.strftime('%d.%m.%Y')}") for item in history.items],
        offset=history.offset,
        has_more=history.has_more,
        subject_user_id=str(subject_user_id) if subject_user_id is not None else None,
        back_callback=back_callback,
    )
    if callback.message:
        await callback.message.answer(text, reply_markup=markup)
    await callback.answer()


def create_progress_photo_router(*, jinja_env: Environment, mediator: RequestMediator) -> Router:
    router = Router(name="progress_photo")

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
        text = jinja_env.get_template("progress_photo_reminder.j2").render(
            weekdays_label=weekdays_label(weekdays),
            local_time=_format_local_time(local_time),
        )
        await _answer(callback, text, reply_markup=progress_photo_reminder_menu_keyboard())

    @router.callback_query(F.data == "pp_menu")
    async def handle_pp_menu(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        weekdays, local_time = await _current_reminder(
            mediator=mediator,
            telegram_user_id=callback.from_user.id,
        )
        text = jinja_env.get_template("progress_photo.j2").render(
            reminder_weekdays_label=weekdays_label(weekdays),
            reminder_time=_format_local_time(local_time),
        )
        await _answer(callback, text, reply_markup=progress_photo_menu_keyboard())

    @router.callback_query(F.data == "pp_skip")
    async def handle_pp_skip(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        await mediator.send(CancelProgressPhotoCaptureCommand(telegram_user_id=callback.from_user.id))
        await callback.answer("Пропущено")

    @router.callback_query(F.data == "pp_log")
    async def handle_pp_log(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        result = await mediator.send(
            StartProgressPhotoCaptureCommand(telegram_user_id=callback.from_user.id),
        )
        intro = jinja_env.get_template("progress_photo_intro.j2").render(resumed=result.resumed)
        profile = await mediator.send(GetProfileQuery(telegram_user_id=callback.from_user.id))
        overview = progress_pose_overview_image_path(sex=profile.sex)
        if overview is not None and callback.message is not None:
            try:
                photo = FSInputFile(path=str(overview))
                if caption_fits_telegram(intro):
                    await callback.message.answer_photo(photo, caption=intro)
                else:
                    await callback.message.answer(intro)
            except Exception:
                logger.exception("failed to send progress pose overview path=%s", overview)
                if callback.message:
                    await callback.message.answer(intro)
        elif callback.message:
            await callback.message.answer(intro)
        await send_angle_prompt(
            message=callback.message,
            jinja_env=jinja_env,
            mediator=mediator,
            telegram_user_id=callback.from_user.id,
            angle=result.next_angle,
        )
        await callback.answer()

    @router.callback_query(F.data == "pp_hist")
    @router.callback_query(F.data.startswith("pp_hist:"))
    async def handle_pp_hist(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        offset = 0
        if ":" in callback.data:
            offset = int(callback.data.split(":", 1)[1])
        await show_progress_photo_history(
            callback=callback,
            jinja_env=jinja_env,
            mediator=mediator,
            telegram_user_id=callback.from_user.id,
            offset=offset,
            back_callback="pp_menu",
        )

    @router.callback_query(F.data.startswith("pp_hist_one:"))
    async def handle_pp_hist_one(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        assert callback.data is not None
        assert callback.message is not None
        set_id = UUID(callback.data.split(":", 1)[1])
        try:
            await send_progress_photo_set(
                message=callback.message,
                mediator=mediator,
                jinja_env=jinja_env,
                telegram_user_id=callback.from_user.id,
                set_id=set_id,
            )
        except DomainError as exc:
            await _answer(callback, str(exc))
            return
        await callback.answer()

    @router.callback_query(F.data == "pp_remind")
    async def handle_pp_remind(callback: CallbackQuery) -> None:
        await _show_reminder_menu(callback)

    @router.callback_query(F.data.startswith("pp_rm_preset:"))
    async def handle_pp_rm_preset(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        preset = callback.data.split(":", 1)[1]
        _, local_time = await _current_reminder(mediator=mediator, telegram_user_id=callback.from_user.id)
        if preset == "weekly":
            weekdays = sorted(DEFAULT_PROGRESS_PHOTO_REMINDER_WEEKDAYS)
        elif preset == "daily":
            weekdays = list(range(1, 8))
        else:
            await callback.answer()
            return
        await mediator.send(
            SetProgressPhotoReminderCommand(
                telegram_user_id=callback.from_user.id,
                local_time=local_time,
                weekdays=weekdays,
            ),
        )
        await _show_reminder_menu(callback)

    @router.callback_query(F.data == "pp_rm_custom")
    async def handle_pp_rm_custom(callback: CallbackQuery) -> None:
        assert callback.from_user is not None
        weekdays, _ = await _current_reminder(mediator=mediator, telegram_user_id=callback.from_user.id)
        draft = set(weekdays)
        _REMINDER_WEEKDAY_DRAFT[callback.from_user.id] = draft
        text = jinja_env.get_template("progress_photo_reminder_days.j2").render()
        await _answer(callback, text, reply_markup=progress_photo_reminder_weekdays_keyboard(draft))

    @router.callback_query(F.data.startswith("pp_rm_day:"))
    async def handle_pp_rm_day(callback: CallbackQuery) -> None:
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
                SetProgressPhotoReminderCommand(
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
        text = jinja_env.get_template("progress_photo_reminder_days.j2").render()
        await callback.message.edit_text(text, reply_markup=progress_photo_reminder_weekdays_keyboard(draft))
        await callback.answer()

    @router.callback_query(F.data == "pp_rm_time")
    async def handle_pp_rm_time(callback: CallbackQuery) -> None:
        text = jinja_env.get_template("progress_photo_reminder_time.j2").render()
        await _answer(callback, text, reply_markup=progress_photo_reminder_time_keyboard())

    @router.callback_query(F.data.startswith("pp_rm_at:"))
    async def handle_pp_rm_at(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        payload = callback.data.split(":", 1)[1]
        weekdays, _ = await _current_reminder(mediator=mediator, telegram_user_id=callback.from_user.id)
        if payload == "custom":
            await mediator.send(
                ExpectInputCommand(
                    telegram_user_id=callback.from_user.id,
                    expected_input=ExpectedInput.PROFILE_FIELD,
                    expected_field="progress_photo_reminder_time",
                ),
            )
            text = jinja_env.get_template("progress_photo_reminder_prompt.j2").render()
            await _answer(callback, text)
            return
        hour_s, minute_s = payload.split(":")
        local_time = time(hour=int(hour_s), minute=int(minute_s))
        await mediator.send(
            SetProgressPhotoReminderCommand(
                telegram_user_id=callback.from_user.id,
                local_time=local_time,
                weekdays=weekdays,
            ),
        )
        await _show_reminder_menu(callback)

    @router.callback_query(F.data.startswith("coach_pp_hist:"))
    async def handle_coach_pp_hist(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        parts = callback.data.split(":")
        client_id = UUID(parts[1])
        offset = int(parts[2]) if len(parts) > 2 else 0
        try:
            await show_progress_photo_history(
                callback=callback,
                jinja_env=jinja_env,
                mediator=mediator,
                telegram_user_id=callback.from_user.id,
                offset=offset,
                subject_user_id=client_id,
                back_callback=f"coach_client:{client_id}",
            )
        except DomainError as exc:
            await _answer(callback, str(exc))

    @router.callback_query(F.data.startswith("coach_pp_one:"))
    async def handle_coach_pp_one(callback: CallbackQuery) -> None:
        assert callback.from_user is not None and callback.data is not None
        assert callback.message is not None
        set_id = UUID(callback.data.split(":", 1)[1])
        try:
            # Authz: GetProgressPhotoSetQuery loads set owner + require_coach_of.
            await send_progress_photo_set(
                message=callback.message,
                mediator=mediator,
                jinja_env=jinja_env,
                telegram_user_id=callback.from_user.id,
                set_id=set_id,
            )
        except DomainError as exc:
            await _answer(callback, str(exc))
            return
        await callback.answer()

    return router


async def apply_progress_photo_reminder_time(
    *,
    mediator: RequestMediator,
    telegram_user_id: int,
    text: str,
) -> None:
    local_time = parse_reminder_time(text)
    weekdays, _ = await _current_reminder(mediator=mediator, telegram_user_id=telegram_user_id)
    await mediator.send(
        SetProgressPhotoReminderCommand(
            telegram_user_id=telegram_user_id,
            local_time=local_time,
            weekdays=weekdays,
        ),
    )
