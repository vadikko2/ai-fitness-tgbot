from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fitness_bot.domain.enums import SessionStatus
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDocument
from fitness_bot.service.models.commands.base import Command, CommandResult


class StartSessionFromTemplateCommand(Command):
    telegram_user_id: int
    overwrite_completed: bool = False


class StartSessionFromTemplateCommandResult(CommandResult):
    session_id: UUID | None = None
    document: WorkoutDocument | None = None
    needs_repeat_confirmation: bool = False


class ProposeWorkoutChangeCommand(Command):
    telegram_user_id: int
    utterance: str


class ProposeWorkoutChangeCommandResult(CommandResult):
    proposal_id: UUID | None = None
    agent_unavailable: bool = False
    schema_failed: bool = False
    reply: str = ""
    document: WorkoutDocument | None = None


class ConfirmExerciseAsPlannedCommand(Command):
    telegram_user_id: int
    slot_position: int


class ConfirmExerciseAsPlannedCommandResult(CommandResult):
    session_id: UUID
    slot: ExerciseSlot
    document: WorkoutDocument


class RecordSlotActualCommand(Command):
    telegram_user_id: int
    slot_position: int
    sets: int
    reps: int | None = None
    duration_seconds: int | None = None
    weight_kg: Decimal | None = None
    note: str = ""


class RecordSlotActualCommandResult(CommandResult):
    session_id: UUID
    slot: ExerciseSlot
    document: WorkoutDocument


class ProposeSlotActualCommand(Command):
    telegram_user_id: int
    utterance: str
    slot_position: int | None = None


class ProposeSlotActualCommandResult(CommandResult):
    proposal_id: UUID | None = None
    agent_unavailable: bool = False
    schema_failed: bool = False
    reply: str = ""
    document: WorkoutDocument | None = None
    slot_position: int | None = None


class BeginSessionCompletionCommand(Command):
    telegram_user_id: int


class BeginSessionCompletionCommandResult(CommandResult):
    session_id: UUID
    document: WorkoutDocument
    session_status: SessionStatus


class RestartOpenSessionCommand(Command):
    telegram_user_id: int


class RestartOpenSessionCommandResult(CommandResult):
    session_id: UUID
    document: WorkoutDocument
    session_status: SessionStatus


class ProposeSessionDeviationCommand(Command):
    telegram_user_id: int
    utterance: str


class ProposeSessionDeviationCommandResult(CommandResult):
    proposal_id: UUID | None = None
    agent_unavailable: bool = False
    schema_failed: bool = False
    reply: str = ""
    document: WorkoutDocument | None = None


class FinalizeSessionCommand(Command):
    telegram_user_id: int


class FinalizeSessionCommandResult(CommandResult):
    session_id: UUID
    document: WorkoutDocument
    session_status: SessionStatus


class GenerateNextSessionCommand(Command):
    telegram_user_id: int


class GenerateNextSessionCommandResult(CommandResult):
    proposal_id: UUID | None = None
    agent_unavailable: bool = False
    schema_failed: bool = False
    reply: str = ""
    document: WorkoutDocument | None = None


class SaveTechniqueVideoCommand(Command):
    telegram_user_id: int
    body: bytes
    content_type: str
    slot_position: int | None = None


class SaveTechniqueVideoCommandResult(CommandResult):
    session_id: UUID
    slot_id: UUID
    slot_position: int
    object_key: str
    replaced: bool
    document: WorkoutDocument
    coach_chat_id: int | None = None
    coach_user_id: UUID | None = None


class RememberTechniqueVideoFileIdCommand(Command):
    telegram_user_id: int
    slot_id: UUID
    telegram_file_id: str


class RememberTechniqueVideoFileIdCommandResult(CommandResult):
    slot_id: UUID
    telegram_file_id: str
