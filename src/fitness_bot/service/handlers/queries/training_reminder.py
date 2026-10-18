from __future__ import annotations

from datetime import UTC, datetime, timedelta

import cqrs

from fitness_bot.domain.enums import ProgramStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User, parse_timezone_offset
from fitness_bot.domain.workout.training_reminder import evening_reminder_due, morning_reminder_due
from fitness_bot.domain.workout.week_progress import training_week_progress
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.queries import training_reminder as queries


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


class GetTrainingReminderSettingsQueryHandler(
    cqrs.RequestHandler[
        queries.GetTrainingReminderSettingsQuery,
        queries.GetTrainingReminderSettingsQueryResult,
    ],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: queries.GetTrainingReminderSettingsQuery,
    ) -> queries.GetTrainingReminderSettingsQueryResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            prefs = await repos.training_reminders.get(user.id)
            if prefs is None:
                return queries.GetTrainingReminderSettingsQueryResult()
            return queries.GetTrainingReminderSettingsQueryResult(
                evening_enabled=prefs.evening_enabled,
                morning_enabled=prefs.morning_enabled,
            )


class ListDueTrainingRemindersQueryHandler(
    cqrs.RequestHandler[
        queries.ListDueTrainingRemindersQuery,
        queries.ListDueTrainingRemindersQueryResult,
    ],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: queries.ListDueTrainingRemindersQuery,
    ) -> queries.ListDueTrainingRemindersQueryResult:
        now = request.now or datetime.now(UTC)
        utc_now = now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
        due: list[queries.DueTrainingReminderItem] = []
        async with self._uow.transaction() as repos:
            reminders = await repos.training_reminders.list_all()
            for prefs in reminders:
                user = await repos.users.get_by_id(prefs.user_id)
                if user is None:
                    continue
                offset = (
                    parse_timezone_offset(user.timezone_offset) if user.timezone_offset is not None else timedelta(0)
                )
                local_dt = utc_now + offset
                kinds: list[queries.TrainingReminderKind] = []
                if prefs.evening_enabled and evening_reminder_due(local_dt, prefs.last_evening_sent_on):
                    kinds.append("evening")
                if prefs.morning_enabled and morning_reminder_due(local_dt, prefs.last_morning_sent_on):
                    kinds.append("morning")
                if not kinds:
                    continue
                if user.active_program_id is None:
                    continue
                program = await repos.programs.get_by_id(user.active_program_id)
                if program is None or program.status != ProgramStatus.ACTIVE:
                    continue
                history = await repos.sessions.list_completed_for_user(user.id, limit=50)
                progress = training_week_progress(
                    program,
                    history,
                    timezone_offset=user.timezone_offset,
                    now=utc_now,
                )
                session_open = False
                if user.active_session_id is not None:
                    session = await repos.sessions.get_by_id(user.active_session_id)
                    session_open = session is not None and session.is_open
                for kind in kinds:
                    if kind == "morning" and session_open:
                        continue
                    target = local_dt.date() + timedelta(days=1) if kind == "evening" else local_dt.date()
                    weekday = target.isoweekday()
                    if weekday in progress.completed_weekdays:
                        continue
                    day = next((item for item in program.days if item.weekday == weekday), None)
                    if day is None:
                        continue
                    due.append(
                        queries.DueTrainingReminderItem(
                            user_id=user.id,
                            telegram_user_id=user.telegram_user_id,
                            chat_id=user.chat_id,
                            kind=kind,
                            target_date=target,
                            sent_on=local_dt.date(),
                            day_title=day.title,
                            weekday=weekday,
                        ),
                    )
        return queries.ListDueTrainingRemindersQueryResult(items=due)
