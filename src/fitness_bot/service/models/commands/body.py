from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from fitness_bot.domain.enums import WeightSource
from fitness_bot.service.models.commands.base import Command, CommandResult


class RecordWeightCommand(Command):
    telegram_user_id: int
    kilograms: Decimal | str | float
    source: WeightSource
    measured_at: datetime | None = None


class RecordWeightCommandResult(CommandResult):
    entry_id: UUID
    kilograms: Decimal


class SetWeightReminderCommand(Command):
    telegram_user_id: int
    local_time: time
    weekdays: list[int]


class SetWeightReminderCommandResult(CommandResult):
    user_id: UUID
    local_time: time
    weekdays: list[int]


class EnsureDefaultWeightReminderCommand(Command):
    """Create Sunday 09:00 reminder if the user has none yet."""

    telegram_user_id: int


class EnsureDefaultWeightReminderCommandResult(CommandResult):
    user_id: UUID
    local_time: time
    weekdays: list[int]
    created: bool


class MarkWeightReminderSentCommand(Command):
    user_id: UUID
    sent_on: date


class MarkWeightReminderSentCommandResult(CommandResult):
    user_id: UUID
    last_sent_on: date


class RecordMeasurementCommand(Command):
    telegram_user_id: int
    site_id: UUID
    centimeters: Decimal | str | float
    measured_at: datetime | None = None


class RecordMeasurementCommandResult(CommandResult):
    entry_id: UUID
    site_id: UUID
    centimeters: Decimal


class AddCustomMeasurementSiteCommand(Command):
    telegram_user_id: int
    name: str


class AddCustomMeasurementSiteCommandResult(CommandResult):
    site_id: UUID
    name: str


class EnsureFixedMeasurementSitesCommand(Command):
    """Idempotent: create eight fixed sites + default guides if missing."""


class EnsureFixedMeasurementSitesCommandResult(CommandResult):
    sites_created: int
    guides_created: int


class SeedMeasurementGuidesCommand(Command):
    """CLI: generate and upsert guides for the eight fixed sites."""


class SeedMeasurementGuidesCommandResult(CommandResult):
    seeded: int
    skipped: int
