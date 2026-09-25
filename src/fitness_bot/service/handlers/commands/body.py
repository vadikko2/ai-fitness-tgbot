from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import cqrs
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from fitness_bot.domain.body.measurement import (
    FIXED_MEASUREMENT_SITES,
    MeasurementEntry,
    MeasurementGuide,
    MeasurementSite,
    default_guide_for,
)
from fitness_bot.domain.body.progress_photo import MAX_PROGRESS_PHOTO_BYTES, ProgressPhotoSet
from fitness_bot.domain.body.reminder import ProgressPhotoReminder, WeightReminder
from fitness_bot.domain.body.weight import WeightEntry
from fitness_bot.domain.body.wellbeing import WellbeingEntry
from fitness_bot.domain.enums import ExpectedInput, ProgressPhotoAngle
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User, local_calendar_date, local_day_bounds
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.commands import body as cmds
from fitness_bot.service.ports.language_model import LanguageModel
from fitness_bot.service.ports.object_storage import ObjectStorage

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


class RecordWeightCommandHandler(cqrs.RequestHandler[cmds.RecordWeightCommand, cmds.RecordWeightCommandResult]):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.RecordWeightCommand) -> cmds.RecordWeightCommandResult:
        measured_at = request.measured_at or datetime.now(UTC)
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            day_start, day_end = local_day_bounds(now=measured_at, timezone_offset=user.timezone_offset)
            entry = WeightEntry.create(
                user_id=user.id,
                kilograms=request.kilograms,
                measured_at=measured_at,
                source=request.source,
            )
            saved = await repos.weights.upsert_for_local_day(entry, day_start=day_start, day_end=day_end)
            if user.expected_input == ExpectedInput.WEIGHT:
                user.clear_expectation()
            elif user.expected_input == ExpectedInput.PROFILE_FIELD and user.expected_field == "weight":
                # Continue onboarding after first weight.
                has_weight = True
                next_field = user.next_missing_field(has_weight=has_weight)
                if next_field is not None:
                    user.expect_input(ExpectedInput.PROFILE_FIELD, expected_field=next_field.value)
                else:
                    user.clear_expectation()
            await repos.users.save(user)
            return cmds.RecordWeightCommandResult(entry_id=saved.id, kilograms=saved.kilograms)


class SetWeightReminderCommandHandler(
    cqrs.RequestHandler[cmds.SetWeightReminderCommand, cmds.SetWeightReminderCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.SetWeightReminderCommand) -> cmds.SetWeightReminderCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            existing = await repos.weight_reminders.get(user.id)
            reminder = WeightReminder.create(
                user_id=user.id,
                local_time=request.local_time,
                weekdays=request.weekdays,
            )
            if existing is not None:
                reminder.last_sent_on = existing.last_sent_on
            saved = await repos.weight_reminders.save(reminder)
            return cmds.SetWeightReminderCommandResult(
                user_id=saved.user_id,
                local_time=saved.local_time,
                weekdays=sorted(saved.weekdays),
            )


class EnsureDefaultWeightReminderCommandHandler(
    cqrs.RequestHandler[
        cmds.EnsureDefaultWeightReminderCommand,
        cmds.EnsureDefaultWeightReminderCommandResult,
    ],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.EnsureDefaultWeightReminderCommand,
    ) -> cmds.EnsureDefaultWeightReminderCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            existing = await repos.weight_reminders.get(user.id)
            if existing is not None:
                return cmds.EnsureDefaultWeightReminderCommandResult(
                    user_id=existing.user_id,
                    local_time=existing.local_time,
                    weekdays=sorted(existing.weekdays),
                    created=False,
                )
            saved = await repos.weight_reminders.save(WeightReminder.default_for_user(user_id=user.id))
            return cmds.EnsureDefaultWeightReminderCommandResult(
                user_id=saved.user_id,
                local_time=saved.local_time,
                weekdays=sorted(saved.weekdays),
                created=True,
            )


class MarkWeightReminderSentCommandHandler(
    cqrs.RequestHandler[cmds.MarkWeightReminderSentCommand, cmds.MarkWeightReminderSentCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.MarkWeightReminderSentCommand) -> cmds.MarkWeightReminderSentCommandResult:
        async with self._uow.transaction() as repos:
            reminder = await repos.weight_reminders.get(request.user_id)
            if reminder is None:
                raise DomainError("weight reminder not found")
            reminder.mark_sent(request.sent_on)
            saved = await repos.weight_reminders.save(reminder)
            assert saved.last_sent_on is not None
            return cmds.MarkWeightReminderSentCommandResult(
                user_id=saved.user_id,
                last_sent_on=saved.last_sent_on,
            )


class RecordMeasurementCommandHandler(
    cqrs.RequestHandler[cmds.RecordMeasurementCommand, cmds.RecordMeasurementCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.RecordMeasurementCommand) -> cmds.RecordMeasurementCommandResult:
        measured_at = request.measured_at or datetime.now(UTC)
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            site = await repos.measurements.get_site_by_id(request.site_id)
            if site is None:
                raise DomainError("measurement site not found")
            if site.is_custom and site.user_id != user.id:
                raise DomainError("custom measurement site belongs to another user")
            entry = MeasurementEntry.create(
                user_id=user.id,
                site_id=site.id,
                centimeters=request.centimeters,
                measured_at=measured_at,
            )
            saved = await repos.measurements.add_entry(entry)
            if user.expected_input == ExpectedInput.MEASUREMENT_VALUE:
                user.clear_expectation()
            await repos.users.save(user)
            return cmds.RecordMeasurementCommandResult(
                entry_id=saved.id,
                site_id=saved.site_id,
                centimeters=saved.centimeters,
            )


class AddCustomMeasurementSiteCommandHandler(
    cqrs.RequestHandler[cmds.AddCustomMeasurementSiteCommand, cmds.AddCustomMeasurementSiteCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.AddCustomMeasurementSiteCommand,
    ) -> cmds.AddCustomMeasurementSiteCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            existing = await repos.measurements.get_custom_site_by_name(user.id, request.name)
            if existing is not None:
                site = existing
            else:
                site = await repos.measurements.add_site(MeasurementSite.custom(user_id=user.id, name=request.name))
            user.expect_input(ExpectedInput.MEASUREMENT_VALUE, expected_field=str(site.id))
            await repos.users.save(user)
            return cmds.AddCustomMeasurementSiteCommandResult(site_id=site.id, name=site.name)


class EnsureFixedMeasurementSitesCommandHandler(
    cqrs.RequestHandler[
        cmds.EnsureFixedMeasurementSitesCommand,
        cmds.EnsureFixedMeasurementSitesCommandResult,
    ],
):
    """Create the eight fixed sites and default guides without calling the LLM."""

    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.EnsureFixedMeasurementSitesCommand,
    ) -> cmds.EnsureFixedMeasurementSitesCommandResult:
        _ = request
        sites_created = 0
        guides_created = 0
        async with self._uow.transaction() as repos:
            for code, name in FIXED_MEASUREMENT_SITES:
                site = await repos.measurements.get_fixed_site_by_code(code)
                if site is None:
                    site = await repos.measurements.add_site(MeasurementSite.fixed(code, name))
                    sites_created += 1
                existing_guide = await repos.measurements.get_guide(site.id)
                if existing_guide is None:
                    await repos.measurements.upsert_guide(
                        MeasurementGuide(site_id=site.id, instruction=default_guide_for(code, name)),
                    )
                    guides_created += 1
        return cmds.EnsureFixedMeasurementSitesCommandResult(
            sites_created=sites_created,
            guides_created=guides_created,
        )


class SeedMeasurementGuidesCommandHandler(
    cqrs.RequestHandler[cmds.SeedMeasurementGuidesCommand, cmds.SeedMeasurementGuidesCommandResult],
):
    def __init__(self, uow: IUow, language_model: LanguageModel) -> None:
        self._uow = uow
        self._language_model = language_model
        self._jinja = Environment(
            loader=FileSystemLoader(str(PROMPTS_DIR)),
            autoescape=False,
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    async def handle(self, request: cmds.SeedMeasurementGuidesCommand) -> cmds.SeedMeasurementGuidesCommandResult:
        seeded = 0
        skipped = 0
        system = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
        template = self._jinja.get_template("measurement_guide_author.md")
        async with self._uow.transaction() as repos:
            for code, name in FIXED_MEASUREMENT_SITES:
                site = await repos.measurements.get_fixed_site_by_code(code)
                if site is None:
                    site = await repos.measurements.add_site(MeasurementSite.fixed(code, name))
                existing_guide = await repos.measurements.get_guide(site.id)
                if existing_guide is not None:
                    skipped += 1
                    continue
                user_prompt = template.render(site_code=code, site_name=name)
                raw = await self._language_model.complete(system=system, user=user_prompt)
                payload = json.loads(raw)
                instruction = str(payload["instruction"])
                await repos.measurements.upsert_guide(MeasurementGuide(site_id=site.id, instruction=instruction))
                seeded += 1
        return cmds.SeedMeasurementGuidesCommandResult(seeded=seeded, skipped=skipped)


class StartProgressPhotoCaptureCommandHandler(
    cqrs.RequestHandler[cmds.StartProgressPhotoCaptureCommand, cmds.StartProgressPhotoCaptureCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.StartProgressPhotoCaptureCommand,
    ) -> cmds.StartProgressPhotoCaptureCommandResult:
        now = request.now or datetime.now(UTC)
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            local_date = local_calendar_date(now=now, timezone_offset=user.timezone_offset)
            incomplete = await repos.progress_photos.get_incomplete_for_user(user.id)
            resumed = False
            if incomplete is not None:
                photo_set = incomplete
                resumed = True
            else:
                existing = await repos.progress_photos.get_for_user_local_date(user.id, local_date)
                if existing is not None:
                    photo_set = existing
                    if photo_set.complete:
                        # Same-day retake: clear angles and walk front → side → back again.
                        photo_set.photos = []
                        photo_set.complete = False
                        photo_set.captured_at = now
                        photo_set = await repos.progress_photos.save_set(photo_set)
                    else:
                        resumed = True
                else:
                    photo_set = ProgressPhotoSet.create(user_id=user.id, local_date=local_date, captured_at=now)
                    photo_set = await repos.progress_photos.save_set(photo_set)
            next_angle = photo_set.next_angle() or ProgressPhotoAngle.FRONT
            user.expect_input(ExpectedInput.PROGRESS_PHOTO, expected_field=next_angle.value)
            await repos.users.save(user)
            return cmds.StartProgressPhotoCaptureCommandResult(
                set_id=photo_set.id,
                local_date=photo_set.local_date,
                next_angle=next_angle.value,
                resumed=resumed,
            )


class RecordProgressPhotoCommandHandler(
    cqrs.RequestHandler[cmds.RecordProgressPhotoCommand, cmds.RecordProgressPhotoCommandResult],
):
    def __init__(self, uow: IUow, object_storage: ObjectStorage) -> None:
        self._uow = uow
        self._object_storage = object_storage

    async def handle(self, request: cmds.RecordProgressPhotoCommand) -> cmds.RecordProgressPhotoCommandResult:
        content_type = (request.content_type or "").strip().lower()
        if not content_type.startswith("image/"):
            raise DomainError("progress photo must be an image/* file")
        byte_size = len(request.body)
        if byte_size <= 0 or byte_size > MAX_PROGRESS_PHOTO_BYTES:
            raise DomainError("progress photo size must be between 1 and 10 MiB")
        now = request.now or datetime.now(UTC)

        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            photo_set = await repos.progress_photos.get_incomplete_for_user(user.id)
            if photo_set is None:
                local_date = local_calendar_date(now=now, timezone_offset=user.timezone_offset)
                photo_set = await repos.progress_photos.get_for_user_local_date(user.id, local_date)
            if photo_set is None:
                raise DomainError("progress photo set not found; start capture first")

            if request.angle is not None:
                angle = ProgressPhotoAngle(request.angle)
            elif user.expected_input == ExpectedInput.PROGRESS_PHOTO and user.expected_field:
                angle = ProgressPhotoAngle(user.expected_field)
            else:
                angle = photo_set.next_angle() or ProgressPhotoAngle.FRONT

            photo, replaced = photo_set.upsert_photo(
                angle=angle,
                content_type=content_type,
                byte_size=byte_size,
                now=now,
            )
            await self._object_storage.put(photo.object_key, request.body, content_type)
            saved = await repos.progress_photos.save_set(photo_set)
            next_angle = saved.next_angle()
            if next_angle is None:
                user.clear_expectation()
            else:
                user.expect_input(ExpectedInput.PROGRESS_PHOTO, expected_field=next_angle.value)
            await repos.users.save(user)
            return cmds.RecordProgressPhotoCommandResult(
                set_id=saved.id,
                photo_id=photo.id,
                angle=angle.value,
                next_angle=next_angle.value if next_angle else None,
                complete=saved.complete,
                replaced=replaced,
            )


class CancelProgressPhotoCaptureCommandHandler(
    cqrs.RequestHandler[cmds.CancelProgressPhotoCaptureCommand, cmds.CancelProgressPhotoCaptureCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.CancelProgressPhotoCaptureCommand,
    ) -> cmds.CancelProgressPhotoCaptureCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            cleared = user.expected_input == ExpectedInput.PROGRESS_PHOTO
            if cleared:
                user.clear_expectation()
                await repos.users.save(user)
            return cmds.CancelProgressPhotoCaptureCommandResult(cleared=cleared)


class RememberProgressPhotoFileIdCommandHandler(
    cqrs.RequestHandler[cmds.RememberProgressPhotoFileIdCommand, cmds.RememberProgressPhotoFileIdCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.RememberProgressPhotoFileIdCommand,
    ) -> cmds.RememberProgressPhotoFileIdCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            photo_set = await repos.progress_photos.get_set(request.set_id)
            if photo_set is None or photo_set.user_id != user.id:
                raise DomainError("progress photo not found")
            updated = photo_set.remember_file_id(
                photo_id=request.photo_id,
                telegram_file_id=request.telegram_file_id,
            )
            await repos.progress_photos.save_set(photo_set)
            return cmds.RememberProgressPhotoFileIdCommandResult(
                photo_id=updated.id,
                telegram_file_id=updated.telegram_file_id or request.telegram_file_id,
            )


class SetProgressPhotoReminderCommandHandler(
    cqrs.RequestHandler[cmds.SetProgressPhotoReminderCommand, cmds.SetProgressPhotoReminderCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.SetProgressPhotoReminderCommand,
    ) -> cmds.SetProgressPhotoReminderCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            existing = await repos.progress_photo_reminders.get(user.id)
            reminder = ProgressPhotoReminder.create(
                user_id=user.id,
                local_time=request.local_time,
                weekdays=request.weekdays,
            )
            if existing is not None:
                reminder.last_sent_on = existing.last_sent_on
            saved = await repos.progress_photo_reminders.save(reminder)
            return cmds.SetProgressPhotoReminderCommandResult(
                user_id=saved.user_id,
                local_time=saved.local_time,
                weekdays=sorted(saved.weekdays),
            )


class EnsureDefaultProgressPhotoReminderCommandHandler(
    cqrs.RequestHandler[
        cmds.EnsureDefaultProgressPhotoReminderCommand,
        cmds.EnsureDefaultProgressPhotoReminderCommandResult,
    ],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.EnsureDefaultProgressPhotoReminderCommand,
    ) -> cmds.EnsureDefaultProgressPhotoReminderCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            existing = await repos.progress_photo_reminders.get(user.id)
            if existing is not None:
                return cmds.EnsureDefaultProgressPhotoReminderCommandResult(
                    user_id=existing.user_id,
                    local_time=existing.local_time,
                    weekdays=sorted(existing.weekdays),
                    created=False,
                )
            saved = await repos.progress_photo_reminders.save(
                ProgressPhotoReminder.default_for_user(user_id=user.id),
            )
            return cmds.EnsureDefaultProgressPhotoReminderCommandResult(
                user_id=saved.user_id,
                local_time=saved.local_time,
                weekdays=sorted(saved.weekdays),
                created=True,
            )


class MarkProgressPhotoReminderSentCommandHandler(
    cqrs.RequestHandler[
        cmds.MarkProgressPhotoReminderSentCommand,
        cmds.MarkProgressPhotoReminderSentCommandResult,
    ],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.MarkProgressPhotoReminderSentCommand,
    ) -> cmds.MarkProgressPhotoReminderSentCommandResult:
        async with self._uow.transaction() as repos:
            reminder = await repos.progress_photo_reminders.get(request.user_id)
            if reminder is None:
                raise DomainError("progress photo reminder not found")
            reminder.mark_sent(request.sent_on)
            saved = await repos.progress_photo_reminders.save(reminder)
            assert saved.last_sent_on is not None
            return cmds.MarkProgressPhotoReminderSentCommandResult(
                user_id=saved.user_id,
                last_sent_on=saved.last_sent_on,
            )


class RecordWellbeingCommandHandler(
    cqrs.RequestHandler[cmds.RecordWellbeingCommand, cmds.RecordWellbeingCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.RecordWellbeingCommand) -> cmds.RecordWellbeingCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            entry = WellbeingEntry.create(user_id=user.id, text=request.text)
            saved = await repos.wellbeing.add(entry)
            if user.expected_input == ExpectedInput.WELLBEING:
                user.clear_expectation()
                await repos.users.save(user)
            return cmds.RecordWellbeingCommandResult(entry_id=saved.id, text=saved.text)
