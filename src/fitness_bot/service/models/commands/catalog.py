from __future__ import annotations

from uuid import UUID

from fitness_bot.domain.enums import ProgramStatus
from fitness_bot.domain.workout.document import WorkoutDocument
from fitness_bot.service.models.commands.base import Command, CommandResult


class SaveProgramDraftCommand(Command):
    telegram_user_id: int
    document: WorkoutDocument
    title: str | None = None
    author_label: str | None = None


class SaveProgramDraftCommandResult(CommandResult):
    program_id: UUID
    status: ProgramStatus


class PublishProgramCommand(Command):
    telegram_user_id: int
    program_id: UUID


class PublishProgramCommandResult(CommandResult):
    program_id: UUID
    distribution_code: str
    title: str


class UnpublishProgramCommand(Command):
    telegram_user_id: int
    program_id: UUID


class UnpublishProgramCommandResult(CommandResult):
    program_id: UUID


class ClaimProgramByCodeCommand(Command):
    telegram_user_id: int
    code: str


class ClaimProgramByCodeCommandResult(CommandResult):
    program_id: UUID
    title: str
    already_claimed: bool = False
    author_label: str | None = None
    source_program_id: UUID | None = None


class ApplyCatalogProgramCommand(Command):
    telegram_user_id: int
    program_id: UUID
    mode: str = "adapt"  # adapt | as_is
    utterance: str | None = None


class ApplyCatalogProgramCommandResult(CommandResult):
    active_program_id: UUID | None = None
    proposal_id: UUID | None = None
    mode: str
    reply: str | None = None
    document: WorkoutDocument | None = None
    adapt_diff: str | None = None


class AssignProgramToClientCommand(Command):
    telegram_user_id: int
    client_user_id: UUID
    program_id: UUID
    mode: str = "as_is"


class AssignProgramToClientCommandResult(CommandResult):
    active_program_id: UUID
    client_user_id: UUID
    client_chat_id: int
    title: str
    proposal_id: UUID | None = None
