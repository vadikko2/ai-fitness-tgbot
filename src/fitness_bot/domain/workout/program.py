from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import ProgramStatus, ProgramType
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.workout.document import WorkoutDay, WorkoutDocument

_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_distribution_code(*, length: int = 8) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


class Program(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    program_type: ProgramType
    status: ProgramStatus = ProgramStatus.ACTIVE
    title: str | None = None
    distribution_code: str | None = None
    published_at: datetime | None = None
    source_program_id: UUID | None = None
    source_author_user_id: UUID | None = None
    assigned_by_user_id: UUID | None = None
    author_label: str | None = None
    days: list[WorkoutDay] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None
    archived_at: datetime | None = None

    @classmethod
    def from_approved_document(
        cls,
        *,
        user_id: UUID,
        document: WorkoutDocument,
        now: datetime | None = None,
        title: str | None = None,
        assigned_by_user_id: UUID | None = None,
        author_label: str | None = None,
        source_program_id: UUID | None = None,
        source_author_user_id: UUID | None = None,
    ) -> Program:
        document.assert_approvable()
        moment = now or datetime.now(UTC)
        return cls(
            user_id=user_id,
            program_type=document.program_type,
            status=ProgramStatus.ACTIVE,
            title=title,
            assigned_by_user_id=assigned_by_user_id,
            author_label=author_label,
            source_program_id=source_program_id,
            source_author_user_id=source_author_user_id,
            days=list(document.days),
            created_at=moment,
            activated_at=moment,
        )

    @classmethod
    def draft_from_document(
        cls,
        *,
        user_id: UUID,
        document: WorkoutDocument,
        title: str | None = None,
        author_label: str | None = None,
        source_program_id: UUID | None = None,
        source_author_user_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Program:
        moment = now or datetime.now(UTC)
        return cls(
            user_id=user_id,
            program_type=document.program_type,
            status=ProgramStatus.DRAFT,
            title=title or "Черновик программы",
            author_label=author_label,
            source_program_id=source_program_id,
            source_author_user_id=source_author_user_id,
            days=list(document.days),
            created_at=moment,
        )

    def to_document(self) -> WorkoutDocument:
        return WorkoutDocument(
            program_type=self.program_type,
            days=list(self.days),
        )

    def display_title(self) -> str:
        if self.title:
            return self.title
        return self.program_type.value.replace("_", " ").title()

    def publish(self, *, code: str | None = None, now: datetime | None = None) -> None:
        if self.status not in {ProgramStatus.DRAFT, ProgramStatus.PUBLISHED}:
            raise DomainError("only draft or published programs can be published")
        self.to_document().assert_approvable()
        moment = now or datetime.now(UTC)
        self.status = ProgramStatus.PUBLISHED
        self.distribution_code = (code or self.distribution_code or generate_distribution_code()).upper()
        self.published_at = moment
        self.archived_at = None

    def unpublish(self, *, now: datetime | None = None) -> None:
        if self.status != ProgramStatus.PUBLISHED:
            raise DomainError("only published programs can be unpublished")
        self.status = ProgramStatus.DRAFT
        self.distribution_code = None
        self.published_at = None
        _ = now

    def archive(self, *, now: datetime | None = None) -> None:
        if self.status != ProgramStatus.ACTIVE:
            raise DomainError("only an active program can be archived")
        self.status = ProgramStatus.ARCHIVED
        self.archived_at = now or datetime.now(UTC)

    def claim_copy_for(
        self,
        *,
        claimant_user_id: UUID,
        author_label: str | None = None,
        now: datetime | None = None,
    ) -> Program:
        if self.status != ProgramStatus.PUBLISHED:
            raise DomainError("only published programs can be claimed")
        if self.user_id == claimant_user_id:
            raise DomainError("cannot claim your own published program")
        moment = now or datetime.now(UTC)
        return Program(
            user_id=claimant_user_id,
            program_type=self.program_type,
            status=ProgramStatus.DRAFT,
            title=self.display_title(),
            source_program_id=self.id,
            source_author_user_id=self.user_id,
            author_label=author_label or self.author_label,
            days=list(self.days),
            created_at=moment,
        )
