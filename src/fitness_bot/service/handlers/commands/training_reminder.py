from __future__ import annotations

from datetime import UTC, datetime

import cqrs

from fitness_bot.domain.enums import ProgramStatus, ProposalKind
from fitness_bot.domain.errors import CannotShiftTrainingDay, DomainError
from fitness_bot.domain.users.user import User, local_calendar_date
from fitness_bot.domain.workout.day_shift import shift_training_day_forward
from fitness_bot.domain.workout.training_reminder import TrainingReminderPrefs
from fitness_bot.domain.workout.week_progress import training_week_progress
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.commands import training_reminder as cmds


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


class ToggleTrainingReminderCommandHandler(
    cqrs.RequestHandler[cmds.ToggleTrainingReminderCommand, cmds.ToggleTrainingReminderCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.ToggleTrainingReminderCommand,
    ) -> cmds.ToggleTrainingReminderCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            prefs = await repos.training_reminders.get(user.id)
            if prefs is None:
                prefs = TrainingReminderPrefs.default_for_user(user_id=user.id)
            prefs.toggle(request.kind)
            saved = await repos.training_reminders.save(prefs)
            return cmds.ToggleTrainingReminderCommandResult(
                evening_enabled=saved.evening_enabled,
                morning_enabled=saved.morning_enabled,
            )


class MarkTrainingReminderSentCommandHandler(
    cqrs.RequestHandler[cmds.MarkTrainingReminderSentCommand, cmds.MarkTrainingReminderSentCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.MarkTrainingReminderSentCommand,
    ) -> cmds.MarkTrainingReminderSentCommandResult:
        async with self._uow.transaction() as repos:
            prefs = await repos.training_reminders.get(request.user_id)
            if prefs is None:
                prefs = TrainingReminderPrefs.default_for_user(user_id=request.user_id)
            prefs.mark_sent(request.kind, request.sent_on)
            saved = await repos.training_reminders.save(prefs)
            return cmds.MarkTrainingReminderSentCommandResult(user_id=saved.user_id)


class DisableTrainingRemindersCommandHandler(
    cqrs.RequestHandler[cmds.DisableTrainingRemindersCommand, cmds.DisableTrainingRemindersCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.DisableTrainingRemindersCommand,
    ) -> cmds.DisableTrainingRemindersCommandResult:
        async with self._uow.transaction() as repos:
            prefs = await repos.training_reminders.get(request.user_id)
            if prefs is None:
                prefs = TrainingReminderPrefs.default_for_user(user_id=request.user_id)
            prefs.disable_all()
            saved = await repos.training_reminders.save(prefs)
            return cmds.DisableTrainingRemindersCommandResult(user_id=saved.user_id)


class SkipTrainingDayCommandHandler(
    cqrs.RequestHandler[cmds.SkipTrainingDayCommand, cmds.SkipTrainingDayCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.SkipTrainingDayCommand) -> cmds.SkipTrainingDayCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            now = datetime.now(UTC)
            today = local_calendar_date(now=now, timezone_offset=user.timezone_offset)
            if request.local_date < today:
                return cmds.SkipTrainingDayCommandResult(outcome="past")
            if user.active_program_id is None:
                return cmds.SkipTrainingDayCommandResult(outcome="no_program")
            program = await repos.programs.get_by_id(user.active_program_id)
            if program is None or program.status != ProgramStatus.ACTIVE:
                return cmds.SkipTrainingDayCommandResult(outcome="no_program")

            weekday = request.local_date.isoweekday()
            if not any(day.weekday == weekday for day in program.days):
                return cmds.SkipTrainingDayCommandResult(outcome="rest")

            if user.active_session_id is not None:
                session = await repos.sessions.get_by_id(user.active_session_id)
                if session is not None and session.is_open and session.day.weekday == weekday:
                    return cmds.SkipTrainingDayCommandResult(outcome="in_progress")

            history = await repos.sessions.list_completed_for_user(user.id, limit=50)
            progress = training_week_progress(program, history, timezone_offset=user.timezone_offset, now=now)
            if weekday in progress.completed_weekdays:
                return cmds.SkipTrainingDayCommandResult(outcome="already_done")

            try:
                new_days, moves = shift_training_day_forward(program.days, weekday)
            except CannotShiftTrainingDay:
                return cmds.SkipTrainingDayCommandResult(outcome="cannot_shift")
            program.days = new_days
            await repos.programs.save(program)

            pending = await repos.proposals.get_pending_for_user(user.id)
            if pending is not None and pending.kind == ProposalKind.NEXT_SESSION:
                pending.discard()
                await repos.proposals.save(pending)
                user.pending_proposal_id = None
                await repos.users.save(user)

            return cmds.SkipTrainingDayCommandResult(
                outcome="shifted",
                moves=[
                    cmds.DayMove(title=move.title, from_weekday=move.from_weekday, to_weekday=move.to_weekday)
                    for move in moves
                ],
            )
