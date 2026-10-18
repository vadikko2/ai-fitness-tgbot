from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fitness_bot.service.models.commands.base import Command, CommandResult

TrainingReminderKind = Literal["evening", "morning"]
SkipTrainingDayOutcome = Literal[
    "shifted",
    "rest",
    "already_done",
    "in_progress",
    "no_program",
    "cannot_shift",
    "past",
]


class ToggleTrainingReminderCommand(Command):
    telegram_user_id: int
    kind: TrainingReminderKind


class ToggleTrainingReminderCommandResult(CommandResult):
    evening_enabled: bool
    morning_enabled: bool


class MarkTrainingReminderSentCommand(Command):
    user_id: UUID
    kind: TrainingReminderKind
    sent_on: date


class MarkTrainingReminderSentCommandResult(CommandResult):
    user_id: UUID


class DisableTrainingRemindersCommand(Command):
    """User blocked the bot — stop both nudges so the scheduler does not retry."""

    user_id: UUID


class DisableTrainingRemindersCommandResult(CommandResult):
    user_id: UUID


class DayMove(CommandResult):
    title: str
    from_weekday: int
    to_weekday: int


class SkipTrainingDayCommand(Command):
    """Shift the planned workout of ``local_date`` onto the next day."""

    telegram_user_id: int
    local_date: date


class SkipTrainingDayCommandResult(CommandResult):
    outcome: SkipTrainingDayOutcome
    moves: list[DayMove] = []
