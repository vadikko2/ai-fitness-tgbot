from __future__ import annotations

from uuid import UUID

from fitness_bot.domain.enums import CoachNoteVisibility, ProgramType
from fitness_bot.domain.workout.document import WorkoutDocument
from fitness_bot.service.models.commands.base import Command, CommandResult


class SubmitCoachApplicationCommand(Command):
    telegram_user_id: int
    display_name: str
    bio: str
    portfolio_url: str
    credential_object_key: str
    credential_content_type: str
    credential_byte_size: int
    credential_caption: str | None = None


class SubmitCoachApplicationCommandResult(CommandResult):
    application_id: UUID
    moderator_user_ids: list[UUID]
    moderator_chats: list[dict] = []
    display_name: str = ""
    bio: str = ""
    portfolio_url: str = ""
    credential_object_key: str = ""
    credential_content_type: str = ""


class ApproveCoachApplicationCommand(Command):
    telegram_user_id: int
    application_id: UUID


class ApproveCoachApplicationCommandResult(CommandResult):
    application_id: UUID
    already_processed: bool = False
    applicant_user_id: UUID | None = None
    applicant_chat_id: int | None = None
    moderator_message_refs: list[dict] = []
    status_text: str = ""


class RejectCoachApplicationCommand(Command):
    telegram_user_id: int
    application_id: UUID
    comment: str


class RejectCoachApplicationCommandResult(CommandResult):
    application_id: UUID
    already_processed: bool = False
    applicant_user_id: UUID | None = None
    applicant_chat_id: int | None = None
    moderator_comment: str | None = None
    moderator_message_refs: list[dict] = []
    status_text: str = ""


class GrantModeratorCommand(Command):
    actor_telegram_user_id: int
    target_telegram_user_id: int


class GrantModeratorCommandResult(CommandResult):
    target_user_id: UUID


class RevokeModeratorCommand(Command):
    actor_telegram_user_id: int
    target_telegram_user_id: int


class RevokeModeratorCommandResult(CommandResult):
    target_user_id: UUID


class CreateCoachInviteCommand(Command):
    telegram_user_id: int


class CreateCoachInviteCommandResult(CommandResult):
    invite_id: UUID
    code: str
    revoked_previous: bool = False


class AcceptCoachInviteCommand(Command):
    telegram_user_id: int
    code: str


class AcceptCoachInviteCommandResult(CommandResult):
    link_id: UUID
    coach_user_id: UUID
    previous_coach_user_id: UUID | None = None


class UnlinkCoachClientCommand(Command):
    telegram_user_id: int
    link_id: UUID | None = None
    client_user_id: UUID | None = None
    coach_user_id: UUID | None = None


class UnlinkCoachClientCommandResult(CommandResult):
    link_id: UUID
    coach_user_id: UUID
    client_user_id: UUID
    other_party_user_id: UUID


class SetAcceptingClientsCommand(Command):
    telegram_user_id: int
    accepting: bool


class SetAcceptingClientsCommandResult(CommandResult):
    accepting_clients: bool


class UpsertCoachReviewCommand(Command):
    telegram_user_id: int
    coach_user_id: UUID
    stars: int
    body: str | None = None


class UpsertCoachReviewCommandResult(CommandResult):
    review_id: UUID
    rating_avg: float | None = None
    rating_count: int = 0


class DeleteCoachReviewCommand(Command):
    telegram_user_id: int
    coach_user_id: UUID


class DeleteCoachReviewCommandResult(CommandResult):
    deleted: bool


class ReportCoachCommand(Command):
    telegram_user_id: int
    coach_user_id: UUID
    body: str


class ReportCoachCommandResult(CommandResult):
    report_id: UUID
    moderator_user_ids: list[UUID]


class ResolveCoachReportCommand(Command):
    telegram_user_id: int
    report_id: UUID
    suspend: bool = False


class ResolveCoachReportCommandResult(CommandResult):
    report_id: UUID
    suspended: bool = False


class CreateCoachNoteCommand(Command):
    telegram_user_id: int
    client_user_id: UUID
    visibility: CoachNoteVisibility
    body: str
    session_id: UUID | None = None
    slot_id: UUID | None = None


class CreateCoachNoteCommandResult(CommandResult):
    note_id: UUID
    visibility: CoachNoteVisibility
    client_chat_id: int | None = None
    coach_username: str | None = None


class SyncUserIdentityCommand(Command):
    telegram_user_id: int
    chat_id: int
    display_name: str | None = None
    telegram_username: str | None = None
    bootstrap_moderator_ids: list[int] = []


class SyncUserIdentityCommandResult(CommandResult):
    user_id: UUID
    is_moderator: bool


class RecordModeratorApplicationMessageCommand(Command):
    application_id: UUID
    moderator_user_id: UUID
    chat_id: int
    message_id: int
    media_message_id: int | None = None


class RecordModeratorApplicationMessageCommandResult(CommandResult):
    message_id: UUID


class StartCoachClientProgramEditCommand(Command):
    telegram_user_id: int
    client_user_id: UUID


class StartCoachClientProgramEditCommandResult(CommandResult):
    client_user_id: UUID
    proposal_id: UUID
    document: WorkoutDocument | None = None
    program_type: ProgramType | None = None
    has_active_program: bool = False
