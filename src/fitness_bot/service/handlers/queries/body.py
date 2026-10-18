from __future__ import annotations

from datetime import UTC, datetime, timedelta

import cqrs

from fitness_bot.domain.body.wellbeing import fresh_unapplied
from fitness_bot.domain.enums import ExpectedInput, ProgressPhotoAngle
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User, local_calendar_date, parse_timezone_offset
from fitness_bot.service.authz import require_coach_of
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.queries import body as queries
from fitness_bot.service.ports.object_storage import ObjectStorage


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


class GetWeightHistoryQueryHandler(
    cqrs.RequestHandler[queries.GetWeightHistoryQuery, queries.GetWeightHistoryQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetWeightHistoryQuery) -> queries.GetWeightHistoryQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            entries = await repos.weights.history_for_user(user.id, limit=request.limit)
            items = [
                queries.WeightHistoryItem(
                    id=entry.id,
                    kilograms=entry.kilograms,
                    measured_on=local_calendar_date(
                        now=entry.measured_at,
                        timezone_offset=user.timezone_offset,
                    ),
                    source=entry.source,
                )
                for entry in entries
            ]
            latest = entries[0].kilograms if entries else None
            return queries.GetWeightHistoryQueryResult(items=items, latest_kg=latest)


class GetWeightReminderQueryHandler(
    cqrs.RequestHandler[queries.GetWeightReminderQuery, queries.GetWeightReminderQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetWeightReminderQuery) -> queries.GetWeightReminderQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            reminder = await repos.weight_reminders.get(user.id)
            if reminder is None:
                return queries.GetWeightReminderQueryResult(local_time=None, weekdays=[])
            return queries.GetWeightReminderQueryResult(
                local_time=reminder.local_time,
                weekdays=sorted(reminder.weekdays),
            )


class GetMeasurementHistoryQueryHandler(
    cqrs.RequestHandler[queries.GetMeasurementHistoryQuery, queries.GetMeasurementHistoryQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: queries.GetMeasurementHistoryQuery,
    ) -> queries.GetMeasurementHistoryQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            sites = await repos.measurements.list_sites_for_user(user.id)
            site_items: list[queries.MeasurementSiteItem] = []
            for site in sites:
                history = await repos.measurements.history_for_user(user.id, site_id=site.id, limit=1)
                site_items.append(
                    queries.MeasurementSiteItem(
                        id=site.id,
                        code=site.code,
                        name=site.name,
                        is_custom=site.is_custom,
                        latest_cm=history[0].centimeters if history else None,
                    ),
                )
            entries = await repos.measurements.history_for_user(
                user.id,
                site_id=request.site_id,
                limit=request.limit,
            )
            sites_by_id = {site.id: site for site in sites}
            history_items = [
                queries.MeasurementHistoryItem(
                    id=entry.id,
                    site_id=entry.site_id,
                    site_name=sites_by_id[entry.site_id].name if entry.site_id in sites_by_id else str(entry.site_id),
                    centimeters=entry.centimeters,
                    measured_at=entry.measured_at,
                )
                for entry in entries
            ]
            return queries.GetMeasurementHistoryQueryResult(sites=site_items, entries=history_items)


class GetMeasurementGuideQueryHandler(
    cqrs.RequestHandler[queries.GetMeasurementGuideQuery, queries.GetMeasurementGuideQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetMeasurementGuideQuery) -> queries.GetMeasurementGuideQueryResult:
        async with self._uow.transaction() as repos:
            site = await repos.measurements.get_site_by_id(request.site_id)
            if site is None:
                raise DomainError("measurement site not found")
            guide = await repos.measurements.get_guide(site.id)
            return queries.GetMeasurementGuideQueryResult(
                site_id=site.id,
                site_code=site.code,
                site_name=site.name,
                instruction=guide.instruction if guide else None,
            )


class ListDueWeightRemindersQueryHandler(
    cqrs.RequestHandler[queries.ListDueWeightRemindersQuery, queries.ListDueWeightRemindersQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.ListDueWeightRemindersQuery) -> queries.ListDueWeightRemindersQueryResult:
        now = request.now or datetime.now(UTC)
        utc_now = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
        due: list[queries.DueWeightReminderItem] = []
        async with self._uow.transaction() as repos:
            reminders = await repos.weight_reminders.list_all()
            for reminder in reminders:
                user = await repos.users.get_by_id(reminder.user_id)
                if user is None:
                    continue
                if user.expected_input != ExpectedInput.NONE:
                    continue
                # Missing offset → UTC (same as local_calendar_date).
                offset = (
                    parse_timezone_offset(user.timezone_offset) if user.timezone_offset is not None else timedelta(0)
                )
                local_dt = utc_now + offset
                local_date = local_dt.date()
                local_weekday = local_date.isoweekday()
                if local_weekday not in reminder.weekdays:
                    continue
                if local_dt.hour != reminder.local_time.hour or local_dt.minute != reminder.local_time.minute:
                    continue
                if reminder.last_sent_on == local_date:
                    continue
                due.append(
                    queries.DueWeightReminderItem(
                        user_id=user.id,
                        telegram_user_id=user.telegram_user_id,
                        chat_id=user.chat_id,
                        local_date=local_date,
                        local_time=reminder.local_time,
                    ),
                )
        return queries.ListDueWeightRemindersQueryResult(items=due)


class GetProgressPhotoHistoryQueryHandler(
    cqrs.RequestHandler[queries.GetProgressPhotoHistoryQuery, queries.GetProgressPhotoHistoryQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: queries.GetProgressPhotoHistoryQuery,
    ) -> queries.GetProgressPhotoHistoryQueryResult:
        offset = max(0, request.offset)
        limit = max(1, min(request.limit, 50))
        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if request.subject_user_id is not None:
                await require_coach_of(repos, actor, request.subject_user_id)
                user = _require_user(await repos.users.get_by_id(request.subject_user_id))
            else:
                user = actor
            items = await repos.progress_photos.list_complete_for_user(
                user.id,
                limit=limit + 1,
                offset=offset,
            )
            page = items[:limit]
            return queries.GetProgressPhotoHistoryQueryResult(
                items=[
                    queries.ProgressPhotoHistoryItem(
                        set_id=item.id,
                        local_date=item.local_date,
                        captured_at=item.captured_at,
                    )
                    for item in page
                ],
                offset=offset,
                limit=limit,
                has_more=len(items) > limit,
                subject_user_id=request.subject_user_id,
            )


class GetProgressPhotoSetQueryHandler(
    cqrs.RequestHandler[queries.GetProgressPhotoSetQuery, queries.GetProgressPhotoSetQueryResult],
):
    def __init__(self, uow: IUow, object_storage: ObjectStorage) -> None:
        self._uow = uow
        self._object_storage = object_storage

    async def handle(self, request: queries.GetProgressPhotoSetQuery) -> queries.GetProgressPhotoSetQueryResult:
        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            photo_set = await repos.progress_photos.get_set(request.set_id)
            if photo_set is None:
                raise DomainError("progress photo set not found")

            if request.subject_user_id is not None:
                if photo_set.user_id != request.subject_user_id:
                    raise DomainError("progress photo set not found")
                await require_coach_of(repos, actor, request.subject_user_id)
                viewing_as_coach = True
                subject_user_id = request.subject_user_id
            elif photo_set.user_id == actor.id:
                viewing_as_coach = False
                subject_user_id = None
            else:
                # Coach drill-down by set id only (callback omits client uuid for Telegram 64-byte limit).
                await require_coach_of(repos, actor, photo_set.user_id)
                viewing_as_coach = True
                subject_user_id = photo_set.user_id

            # Prefer bytes for coach viewers (file_id is chat-bound to the athlete).
            prefer_file_id = not viewing_as_coach
            deliveries: list[queries.ProgressPhotoDeliveryItem] = []
            for angle in (
                ProgressPhotoAngle.FRONT,
                ProgressPhotoAngle.SIDE,
                ProgressPhotoAngle.BACK,
            ):
                photo = photo_set.photo_for(angle)
                if photo is None:
                    deliveries.append(
                        queries.ProgressPhotoDeliveryItem(
                            angle=angle,
                            content_type="image/jpeg",
                            missing=True,
                        ),
                    )
                    continue
                if prefer_file_id and photo.telegram_file_id:
                    deliveries.append(
                        queries.ProgressPhotoDeliveryItem(
                            photo_id=photo.id,
                            angle=photo.angle,
                            content_type=photo.content_type,
                            telegram_file_id=photo.telegram_file_id,
                        ),
                    )
                    continue
                try:
                    body = await self._object_storage.get(photo.object_key)
                except KeyError:
                    deliveries.append(
                        queries.ProgressPhotoDeliveryItem(
                            photo_id=photo.id,
                            angle=photo.angle,
                            content_type=photo.content_type,
                            missing=True,
                        ),
                    )
                    continue
                deliveries.append(
                    queries.ProgressPhotoDeliveryItem(
                        photo_id=photo.id,
                        angle=photo.angle,
                        content_type=photo.content_type,
                        body=body,
                    ),
                )
            return queries.GetProgressPhotoSetQueryResult(
                set_id=photo_set.id,
                local_date=photo_set.local_date,
                complete=photo_set.complete,
                photos=deliveries,
                subject_user_id=subject_user_id,
            )


class GetProgressPhotoReminderQueryHandler(
    cqrs.RequestHandler[queries.GetProgressPhotoReminderQuery, queries.GetProgressPhotoReminderQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: queries.GetProgressPhotoReminderQuery,
    ) -> queries.GetProgressPhotoReminderQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            reminder = await repos.progress_photo_reminders.get(user.id)
            if reminder is None:
                return queries.GetProgressPhotoReminderQueryResult(local_time=None, weekdays=[])
            return queries.GetProgressPhotoReminderQueryResult(
                local_time=reminder.local_time,
                weekdays=sorted(reminder.weekdays),
            )


class ListDueProgressPhotoRemindersQueryHandler(
    cqrs.RequestHandler[
        queries.ListDueProgressPhotoRemindersQuery,
        queries.ListDueProgressPhotoRemindersQueryResult,
    ],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: queries.ListDueProgressPhotoRemindersQuery,
    ) -> queries.ListDueProgressPhotoRemindersQueryResult:
        now = request.now or datetime.now(UTC)
        utc_now = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
        due: list[queries.DueProgressPhotoReminderItem] = []
        async with self._uow.transaction() as repos:
            reminders = await repos.progress_photo_reminders.list_all()
            for reminder in reminders:
                user = await repos.users.get_by_id(reminder.user_id)
                if user is None:
                    continue
                if user.expected_input != ExpectedInput.NONE:
                    continue
                offset = (
                    parse_timezone_offset(user.timezone_offset) if user.timezone_offset is not None else timedelta(0)
                )
                local_dt = utc_now + offset
                local_date = local_dt.date()
                local_weekday = local_date.isoweekday()
                if local_weekday not in reminder.weekdays:
                    continue
                if local_dt.hour != reminder.local_time.hour or local_dt.minute != reminder.local_time.minute:
                    continue
                if reminder.last_sent_on == local_date:
                    continue
                due.append(
                    queries.DueProgressPhotoReminderItem(
                        user_id=user.id,
                        telegram_user_id=user.telegram_user_id,
                        chat_id=user.chat_id,
                        local_date=local_date,
                        local_time=reminder.local_time,
                    ),
                )
        return queries.ListDueProgressPhotoRemindersQueryResult(items=due)


class GetWellbeingHistoryQueryHandler(
    cqrs.RequestHandler[queries.GetWellbeingHistoryQuery, queries.GetWellbeingHistoryQueryResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: queries.GetWellbeingHistoryQuery) -> queries.GetWellbeingHistoryQueryResult:
        offset = max(0, request.offset)
        limit = max(1, min(request.limit, 30))
        now = datetime.now(UTC)
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            shift = parse_timezone_offset(user.timezone_offset) if user.timezone_offset else timedelta(0)
            entries = await repos.wellbeing.list_page(user.id, offset=offset, limit=limit + 1)
            fresh = fresh_unapplied(
                await repos.wellbeing.list_unapplied(user.id, limit=1),
                now=now,
            )
            page = entries[:limit]
            items = [
                queries.WellbeingHistoryItem(
                    id=entry.id,
                    text=entry.text,
                    created_local=(entry.created_at.astimezone(UTC) + shift).replace(tzinfo=None),
                    applied_on=(
                        local_calendar_date(now=entry.applied_at, timezone_offset=user.timezone_offset)
                        if entry.applied_at is not None
                        else None
                    ),
                    is_fresh=not entry.is_applied and entry.is_fresh(now=now),
                )
                for entry in page
            ]
            return queries.GetWellbeingHistoryQueryResult(
                items=items,
                offset=offset,
                limit=limit,
                has_more=len(entries) > limit,
                has_fresh_unapplied=bool(fresh),
            )
