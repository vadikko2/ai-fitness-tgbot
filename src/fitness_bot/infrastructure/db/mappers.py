from __future__ import annotations

import json

from fitness_bot.domain.body.measurement import MeasurementEntry, MeasurementGuide, MeasurementSite
from fitness_bot.domain.body.progress_photo import ProgressPhoto, ProgressPhotoSet
from fitness_bot.domain.body.reminder import ProgressPhotoReminder, WeightReminder
from fitness_bot.domain.body.weight import WeightEntry
from fitness_bot.domain.enums import (
    ActivityLevel,
    ExpectedInput,
    ExperienceLevel,
    Goal,
    ProgressPhotoAngle,
    Sex,
    TrainingPlace,
    WeightSource,
)
from fitness_bot.domain.users.user import User
from fitness_bot.infrastructure.db.models import (
    MeasurementEntryRow,
    MeasurementGuideRow,
    MeasurementSiteRow,
    ProgressPhotoReminderRow,
    ProgressPhotoReminderWeekdayRow,
    ProgressPhotoRow,
    ProgressPhotoSetRow,
    UserRow,
    UserTrainingWeekdayRow,
    WeightEntryRow,
    WeightReminderRow,
    WeightReminderWeekdayRow,
)


def _supplements_to_domain(raw: str | None) -> frozenset[str] | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return frozenset()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [part.strip() for part in text.split(",") if part.strip()]
    if not isinstance(payload, list):
        return frozenset()
    return frozenset(str(item) for item in payload)


def _supplements_to_row(value: frozenset[str] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(sorted(value), ensure_ascii=False)


def user_to_domain(row: UserRow) -> User:
    return User(
        id=row.id,
        telegram_user_id=row.telegram_user_id,
        chat_id=row.chat_id,
        display_name=row.display_name,
        telegram_username=row.telegram_username,
        is_moderator=row.is_moderator,
        sex=Sex(row.sex) if row.sex else None,
        birth_year=row.birth_year,
        height_cm=row.height_cm,
        experience=ExperienceLevel(row.experience) if row.experience else None,
        experience_details=row.experience_details,
        days_per_week=row.days_per_week,
        training_weekdays=frozenset(item.weekday for item in row.training_weekdays),
        equipment=row.equipment,
        training_place=TrainingPlace(row.training_place) if row.training_place else None,
        limitations=row.limitations,
        activity_level=ActivityLevel(row.activity_level) if row.activity_level else None,
        session_minutes=row.session_minutes,
        body_fat_pct=row.body_fat_pct,
        body_fat_set=row.body_fat_set,
        supplements=_supplements_to_domain(row.supplements),
        supplements_other=row.supplements_other,
        diet_prefs=row.diet_prefs,
        nutrition_constraints=row.nutrition_constraints,
        pharma=row.pharma,
        timezone_offset=row.timezone_offset,
        goal=Goal(row.goal) if row.goal else None,
        nutrition_stale=row.nutrition_stale,
        expected_input=ExpectedInput(row.expected_input),
        expected_field=row.expected_field,
        focus_slot=row.focus_slot,
        active_program_id=row.active_program_id,
        active_session_id=row.active_session_id,
        pending_proposal_id=row.pending_proposal_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def apply_user_to_row(row: UserRow, user: User) -> None:
    row.telegram_user_id = user.telegram_user_id
    row.chat_id = user.chat_id
    row.display_name = user.display_name
    row.telegram_username = user.telegram_username
    row.is_moderator = user.is_moderator
    row.sex = user.sex.value if user.sex else None
    row.birth_year = user.birth_year
    row.height_cm = user.height_cm
    row.experience = user.experience.value if user.experience else None
    row.experience_details = user.experience_details
    row.days_per_week = user.days_per_week
    row.equipment = user.equipment
    row.training_place = user.training_place.value if user.training_place else None
    row.limitations = user.limitations
    row.activity_level = user.activity_level.value if user.activity_level else None
    row.session_minutes = user.session_minutes
    row.body_fat_pct = user.body_fat_pct
    row.body_fat_set = user.body_fat_set
    row.supplements = _supplements_to_row(user.supplements)
    row.supplements_other = user.supplements_other
    row.diet_prefs = user.diet_prefs
    row.nutrition_constraints = user.nutrition_constraints
    row.pharma = user.pharma
    row.timezone_offset = user.timezone_offset
    row.goal = user.goal.value if user.goal else None
    row.nutrition_stale = user.nutrition_stale
    row.expected_input = user.expected_input.value
    row.expected_field = user.expected_field
    row.focus_slot = user.focus_slot
    row.active_program_id = user.active_program_id
    row.active_session_id = user.active_session_id
    row.pending_proposal_id = user.pending_proposal_id
    row.updated_at = user.updated_at
    existing = {item.weekday: item for item in row.training_weekdays}
    desired = set(user.training_weekdays)
    for weekday, item in list(existing.items()):
        if weekday not in desired:
            row.training_weekdays.remove(item)
    for weekday in desired:
        if weekday not in existing:
            row.training_weekdays.append(UserTrainingWeekdayRow(user_id=user.id, weekday=weekday))


def weight_to_domain(row: WeightEntryRow) -> WeightEntry:
    return WeightEntry(
        id=row.id,
        user_id=row.user_id,
        kilograms=row.kilograms,
        measured_at=row.measured_at,
        source=WeightSource(row.source),
    )


def reminder_to_domain(row: WeightReminderRow) -> WeightReminder:
    return WeightReminder(
        user_id=row.user_id,
        local_time=row.local_time,
        weekdays=frozenset(item.weekday for item in row.weekdays),
        last_sent_on=row.last_sent_on,
    )


def site_to_domain(row: MeasurementSiteRow) -> MeasurementSite:
    return MeasurementSite(
        id=row.id,
        code=row.code,
        name=row.name,
        is_custom=row.is_custom,
        user_id=row.user_id,
    )


def guide_to_domain(row: MeasurementGuideRow) -> MeasurementGuide:
    return MeasurementGuide(site_id=row.site_id, instruction=row.instruction)


def measurement_to_domain(row: MeasurementEntryRow) -> MeasurementEntry:
    return MeasurementEntry(
        id=row.id,
        user_id=row.user_id,
        site_id=row.site_id,
        centimeters=row.centimeters,
        measured_at=row.measured_at,
    )


def new_weight_row(entry: WeightEntry) -> WeightEntryRow:
    return WeightEntryRow(
        id=entry.id,
        user_id=entry.user_id,
        kilograms=entry.kilograms,
        measured_at=entry.measured_at,
        source=entry.source.value,
    )


def apply_weight_to_row(row: WeightEntryRow, entry: WeightEntry) -> None:
    row.kilograms = entry.kilograms
    row.measured_at = entry.measured_at
    row.source = entry.source.value


def new_site_row(site: MeasurementSite) -> MeasurementSiteRow:
    return MeasurementSiteRow(
        id=site.id,
        code=site.code,
        name=site.name,
        is_custom=site.is_custom,
        user_id=site.user_id,
    )


def new_measurement_row(entry: MeasurementEntry) -> MeasurementEntryRow:
    return MeasurementEntryRow(
        id=entry.id,
        user_id=entry.user_id,
        site_id=entry.site_id,
        centimeters=entry.centimeters,
        measured_at=entry.measured_at,
    )


def apply_reminder_to_row(row: WeightReminderRow, reminder: WeightReminder) -> None:
    row.local_time = reminder.local_time
    row.last_sent_on = reminder.last_sent_on
    existing = {item.weekday: item for item in row.weekdays}
    desired = set(reminder.weekdays)
    for weekday, item in list(existing.items()):
        if weekday not in desired:
            row.weekdays.remove(item)
    for weekday in desired:
        if weekday not in existing:
            row.weekdays.append(WeightReminderWeekdayRow(user_id=reminder.user_id, weekday=weekday))


def progress_photo_to_domain(row: ProgressPhotoRow) -> ProgressPhoto:
    return ProgressPhoto(
        id=row.id,
        set_id=row.set_id,
        angle=ProgressPhotoAngle(row.angle),
        object_key=row.object_key,
        content_type=row.content_type,
        byte_size=row.byte_size,
        telegram_file_id=row.telegram_file_id,
    )


def progress_photo_set_to_domain(row: ProgressPhotoSetRow) -> ProgressPhotoSet:
    return ProgressPhotoSet(
        id=row.id,
        user_id=row.user_id,
        captured_at=row.captured_at,
        local_date=row.local_date,
        complete=row.complete,
        photos=[progress_photo_to_domain(photo) for photo in row.photos],
    )


def apply_progress_photo_set_to_row(row: ProgressPhotoSetRow, photo_set: ProgressPhotoSet) -> None:
    row.captured_at = photo_set.captured_at
    row.local_date = photo_set.local_date
    row.complete = photo_set.complete
    existing = {item.angle: item for item in row.photos}
    desired = {photo.angle.value: photo for photo in photo_set.photos}
    for angle, item in list(existing.items()):
        if angle not in desired:
            row.photos.remove(item)
    for angle, photo in desired.items():
        if angle in existing:
            item = existing[angle]
            item.id = photo.id
            item.object_key = photo.object_key
            item.content_type = photo.content_type
            item.byte_size = photo.byte_size
            item.telegram_file_id = photo.telegram_file_id
        else:
            row.photos.append(
                ProgressPhotoRow(
                    id=photo.id,
                    set_id=photo_set.id,
                    angle=photo.angle.value,
                    object_key=photo.object_key,
                    content_type=photo.content_type,
                    byte_size=photo.byte_size,
                    telegram_file_id=photo.telegram_file_id,
                ),
            )


def progress_photo_reminder_to_domain(row: ProgressPhotoReminderRow) -> ProgressPhotoReminder:
    return ProgressPhotoReminder(
        user_id=row.user_id,
        local_time=row.local_time,
        weekdays=frozenset(item.weekday for item in row.weekdays),
        last_sent_on=row.last_sent_on,
    )


def apply_progress_photo_reminder_to_row(
    row: ProgressPhotoReminderRow,
    reminder: ProgressPhotoReminder,
) -> None:
    row.local_time = reminder.local_time
    row.last_sent_on = reminder.last_sent_on
    existing = {item.weekday: item for item in row.weekdays}
    desired = set(reminder.weekdays)
    for weekday, item in list(existing.items()):
        if weekday not in desired:
            row.weekdays.remove(item)
    for weekday in desired:
        if weekday not in existing:
            row.weekdays.append(
                ProgressPhotoReminderWeekdayRow(user_id=reminder.user_id, weekday=weekday),
            )
