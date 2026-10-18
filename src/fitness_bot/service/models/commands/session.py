from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fitness_bot.domain.enums import SessionStatus
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDocument
from fitness_bot.service.models.commands.base import Command, CommandResult


class StartSessionFromTemplateCommand(Command):
    telegram_user_id: int
    overwrite_completed: bool = False
    weekday: int | None = None


class StartSessionFromTemplateCommandResult(CommandResult):
    session_id: UUID | None = None
    document: WorkoutDocument | None = None
    needs_repeat_confirmation: bool = False


StartTodayOutcome = Literal["started", "resumed", "already_done", "rest", "no_program"]


class StartTodayWorkoutCommand(Command):
    """One-tap start: resume the open session or start the planned day right away.

    ``weekday`` starts another program day instead of today's (e.g. on a rest day).
    """

    telegram_user_id: int
    weekday: int | None = None


class StartTodayWorkoutCommandResult(CommandResult):
    outcome: StartTodayOutcome
    session_id: UUID | None = None
    session_status: SessionStatus | None = None
    document: WorkoutDocument | None = None
    weekday: int | None = None
    alternative_weekday: int | None = None
    alternative_title: str | None = None
    has_unapplied_wellbeing: bool = False
    wellbeing_note: str | None = None
    week_finished: bool = False
    planned_count: int = 0
    completed_count: int = 0


class SwapSessionSlotExerciseCommand(Command):
    """Swap one not-yet-logged exercise of the open session (today only)."""

    telegram_user_id: int
    slot_position: int
    exercise_id: UUID


class SwapSessionSlotExerciseCommandResult(CommandResult):
    session_id: UUID
    document: WorkoutDocument
    slot: ExerciseSlot
    previous_exercise_id: UUID | None = None
    weight_source: Literal["program", "history", "none"] = "none"
    matches_program: bool = False
    can_replace_in_program: bool = False


class ReplaceProgramSlotFromSessionCommand(Command):
    """Copy the swapped exercise of an open-session slot into the active program day."""

    telegram_user_id: int
    slot_position: int


class ReplaceProgramSlotFromSessionCommandResult(CommandResult):
    program_id: UUID
    day_title: str
    exercise_id: UUID


class ProposeWorkoutChangeCommand(Command):
    telegram_user_id: int
    utterance: str
    adapt_for_wellbeing: bool = False


class ProposeWorkoutChangeCommandResult(CommandResult):
    proposal_id: UUID | None = None
    agent_unavailable: bool = False
    schema_failed: bool = False
    reply: str = ""
    document: WorkoutDocument | None = None
    wellbeing_entry_ids: list[UUID] = []


class ConfirmExerciseAsPlannedCommand(Command):
    telegram_user_id: int
    slot_position: int


class ConfirmExerciseAsPlannedCommandResult(CommandResult):
    session_id: UUID
    slot: ExerciseSlot
    document: WorkoutDocument


class ClearSlotActualCommand(Command):
    telegram_user_id: int
    slot_position: int


class ClearSlotActualCommandResult(CommandResult):
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
    adapt_for_wellbeing: bool = False
    # None keeps today's weekday. Evening «Да, завтра» passes tomorrow's weekday
    # so the draft is that day, not whatever is planned for today.
    target_weekday: int | None = None


class GenerateNextSessionCommandResult(CommandResult):
    proposal_id: UUID | None = None
    agent_unavailable: bool = False
    schema_failed: bool = False
    reply: str = ""
    document: WorkoutDocument | None = None
    wellbeing_entry_ids: list[UUID] = []


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
