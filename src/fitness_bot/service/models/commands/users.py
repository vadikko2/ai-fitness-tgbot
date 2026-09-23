from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fitness_bot.domain.enums import ExpectedInput, Goal, ProfileField
from fitness_bot.service.models.commands.base import Command, CommandResult


class EnsureUserCommand(Command):
    telegram_user_id: int
    chat_id: int


class EnsureUserCommandResult(CommandResult):
    user_id: UUID
    created: bool


class UpdateProfileCommand(Command):
    telegram_user_id: int
    field: ProfileField
    value: str | int | float | list[int] | list[str] | dict[str, object] | None
    now: datetime | None = None


class UpdateProfileCommandResult(CommandResult):
    user_id: UUID
    next_field: ProfileField | None
    profile_complete: bool


class SetGoalCommand(Command):
    telegram_user_id: int
    goal: Goal


class SetGoalCommandResult(CommandResult):
    user_id: UUID
    goal: Goal
    nutrition_stale: bool


class ExpectInputCommand(Command):
    telegram_user_id: int
    expected_input: ExpectedInput
    expected_field: str | None = None
    focus_slot: int | None = None
    pending_site_id: UUID | None = None


class ExpectInputCommandResult(CommandResult):
    user_id: UUID
    expected_input: ExpectedInput
    expected_field: str | None
