from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import ProgramType, ProposalKind, ProposalStatus
from fitness_bot.domain.errors import DomainError, InvalidWorkoutDocument
from fitness_bot.domain.workout.document import WorkoutDocument


class Proposal(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    kind: ProposalKind
    status: ProposalStatus = ProposalStatus.PENDING
    program_type: ProgramType | None = None
    base_program_id: UUID | None = None
    base_session_id: UUID | None = None
    document: WorkoutDocument | None = None
    reply: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def new_program_type(cls, *, user_id: UUID, program_type: ProgramType) -> Proposal:
        return cls(
            user_id=user_id,
            kind=ProposalKind.PROGRAM,
            program_type=program_type,
            document=None,
        )

    @classmethod
    def new_program_document(
        cls,
        *,
        user_id: UUID,
        program_type: ProgramType,
        document: WorkoutDocument,
        reply: str = "",
        base_program_id: UUID | None = None,
    ) -> Proposal:
        if document.program_type != program_type:
            raise InvalidWorkoutDocument("document.program_type must match proposal.program_type")
        return cls(
            user_id=user_id,
            kind=ProposalKind.PROGRAM,
            program_type=program_type,
            document=document.without_slot_ids(),
            reply=reply,
            base_program_id=base_program_id,
        )

    @classmethod
    def new_workout_edit(
        cls,
        *,
        user_id: UUID,
        document: WorkoutDocument,
        base_session_id: UUID,
        reply: str = "",
    ) -> Proposal:
        if len(document.days) != 1:
            raise InvalidWorkoutDocument("workout edit proposal requires exactly one day")
        return cls(
            user_id=user_id,
            kind=ProposalKind.WORKOUT_EDIT,
            program_type=document.program_type,
            document=document.without_slot_ids(),
            reply=reply,
            base_session_id=base_session_id,
        )

    @classmethod
    def new_performance(
        cls,
        *,
        user_id: UUID,
        document: WorkoutDocument,
        base_session_id: UUID,
        reply: str = "",
    ) -> Proposal:
        if len(document.days) != 1:
            raise InvalidWorkoutDocument("performance proposal requires exactly one day")
        return cls(
            user_id=user_id,
            kind=ProposalKind.PERFORMANCE,
            program_type=document.program_type,
            document=document.without_slot_ids(),
            reply=reply,
            base_session_id=base_session_id,
        )

    @classmethod
    def new_completion_deviation(
        cls,
        *,
        user_id: UUID,
        document: WorkoutDocument,
        base_session_id: UUID,
        reply: str = "",
    ) -> Proposal:
        if len(document.days) != 1:
            raise InvalidWorkoutDocument("completion deviation proposal requires exactly one day")
        return cls(
            user_id=user_id,
            kind=ProposalKind.COMPLETION_DEVIATION,
            program_type=document.program_type,
            document=document.without_slot_ids(),
            reply=reply,
            base_session_id=base_session_id,
        )

    @classmethod
    def new_next_session(
        cls,
        *,
        user_id: UUID,
        document: WorkoutDocument,
        base_program_id: UUID,
        reply: str = "",
    ) -> Proposal:
        if len(document.days) != 1:
            raise InvalidWorkoutDocument("next session proposal requires exactly one day")
        return cls(
            user_id=user_id,
            kind=ProposalKind.NEXT_SESSION,
            program_type=document.program_type,
            document=document.without_slot_ids(),
            reply=reply,
            base_program_id=base_program_id,
        )

    def replace_document(self, document: WorkoutDocument, *, reply: str = "") -> None:
        if self.kind == ProposalKind.PROGRAM:
            if self.program_type is None:
                raise DomainError("program proposal requires program_type")
            if document.program_type != self.program_type:
                document = document.model_copy(update={"program_type": self.program_type})
        elif self.kind in {
            ProposalKind.WORKOUT_EDIT,
            ProposalKind.PERFORMANCE,
            ProposalKind.COMPLETION_DEVIATION,
            ProposalKind.NEXT_SESSION,
        }:
            if len(document.days) != 1:
                raise InvalidWorkoutDocument(f"{self.kind.value} proposal requires exactly one day")
            self.program_type = document.program_type
        self.document = document.without_slot_ids()
        self.reply = reply
        self.status = ProposalStatus.PENDING

    def approve(self) -> WorkoutDocument:
        if self.status != ProposalStatus.PENDING:
            raise DomainError("only pending proposals can be approved")
        if self.document is None:
            raise DomainError("proposal has no document to approve")
        self.document.assert_approvable(require_schedule=self.kind == ProposalKind.PROGRAM)
        self.status = ProposalStatus.APPROVED
        return self.document

    def discard(self) -> None:
        if self.status != ProposalStatus.PENDING:
            raise DomainError("only pending proposals can be discarded")
        self.status = ProposalStatus.DISCARDED
