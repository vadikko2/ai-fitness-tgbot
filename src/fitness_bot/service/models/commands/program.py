from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fitness_bot.domain.enums import ProgramType
from fitness_bot.domain.workout.document import WorkoutDocument
from fitness_bot.service.models.commands.base import Command, CommandResult


class ChooseProgramTypeCommand(Command):
    telegram_user_id: int
    program_type: ProgramType


class ChooseProgramTypeCommandResult(CommandResult):
    proposal_id: UUID
    program_type: ProgramType


class ProposeProgramCommand(Command):
    telegram_user_id: int


class ProposeProgramCommandResult(CommandResult):
    proposal_id: UUID | None = None
    agent_unavailable: bool = False
    schema_failed: bool = False
    reply: str = ""
    document: WorkoutDocument | None = None


class ProposeProgramChangeCommand(Command):
    telegram_user_id: int
    utterance: str
    day_position: int | None = None
    subject_user_id: UUID | None = None


class ProposeProgramChangeCommandResult(CommandResult):
    proposal_id: UUID | None = None
    agent_unavailable: bool = False
    schema_failed: bool = False
    reply: str = ""
    document: WorkoutDocument | None = None
    day_position: int | None = None
    subject_user_id: UUID | None = None


class SelectExerciseForProposalCommand(Command):
    telegram_user_id: int
    day_position: int
    slot_position: int
    exercise_id: UUID


class SelectExerciseForProposalCommandResult(CommandResult):
    proposal_id: UUID
    document: WorkoutDocument


class UpdateProposalSlotPlannedCommand(Command):
    telegram_user_id: int
    day_position: int
    slot_position: int
    weight_kg: Decimal | None = None
    reps: int | None = None
    duration_seconds: int | None = None


class UpdateProposalSlotPlannedCommandResult(CommandResult):
    proposal_id: UUID
    document: WorkoutDocument
    day_position: int
    slot_position: int


class ApproveProposalCommand(Command):
    telegram_user_id: int
    subject_user_id: UUID | None = None


class ApproveProposalCommandResult(CommandResult):
    program_id: UUID | None = None
    session_id: UUID | None = None
    proposal_id: UUID
    nutrition_stale: bool = False
    blocked_unresolved: bool = False
    blocked_empty: bool = False
    blocked_schedule: bool = False
    document: WorkoutDocument | None = None
    client_chat_id: int | None = None
    program_title: str | None = None
    subject_user_id: UUID | None = None


class DiscardProposalCommand(Command):
    telegram_user_id: int
    subject_user_id: UUID | None = None


class DiscardProposalCommandResult(CommandResult):
    proposal_id: UUID
    subject_user_id: UUID | None = None


class GenerateNextWeekCommand(Command):
    telegram_user_id: int


class GenerateNextWeekCommandResult(CommandResult):
    proposal_id: UUID | None = None
    agent_unavailable: bool = False
    schema_failed: bool = False
    reply: str = ""
    document: WorkoutDocument | None = None
