from __future__ import annotations

from datetime import UTC, datetime, timedelta

import cqrs

from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User, local_calendar_date, parse_timezone_offset
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.queries import body as queries


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
