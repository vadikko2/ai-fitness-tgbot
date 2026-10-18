from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import ProgramStatus, ProgramType
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.program_catalog import program_type_label
from fitness_bot.domain.workout.document import WorkoutDay, WorkoutDocument

_CODE_ALPHABET = string.ascii_uppercase + string.digits
LIBRARY_TITLE_MAX_LENGTH = 60
LIBRARY_CARD_STATUSES = frozenset({ProgramStatus.DRAFT, ProgramStatus.PUBLISHED})


def _days_per_week_label(count: int) -> str:
    tail10, tail100 = count % 10, count % 100
    if tail10 == 1 and tail100 != 11:
        word = "день"
    elif 2 <= tail10 <= 4 and not 12 <= tail100 <= 14:
        word = "дня"
    else:
        word = "дней"
    return f"{count} {word}"


def default_library_title(document: WorkoutDocument, *, now: datetime | None = None) -> str:
    """Auto-name for a saved card: type · days/week · date, so same-type cards differ."""
    moment = now or datetime.now(UTC)
    parts = [program_type_label(document.program_type)]
    if document.days:
        parts.append(_days_per_week_label(len(document.days)))
    parts.append(moment.strftime("%d.%m.%Y"))
    return " · ".join(parts)


def unique_library_title(title: str, taken: set[str]) -> str:
    if title not in taken:
        return title
    index = 2
    while f"{title} ({index})" in taken:
        index += 1
    return f"{title} ({index})"


def normalize_library_title(raw: str) -> str:
    title = " ".join(raw.split())
    if not title:
        raise DomainError("program title must not be empty")
    if len(title) > LIBRARY_TITLE_MAX_LENGTH:
        raise DomainError(f"program title must be at most {LIBRARY_TITLE_MAX_LENGTH} characters")
    return title


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
        detached = document.without_slot_ids()
        return cls(
            user_id=user_id,
            program_type=detached.program_type,
            status=ProgramStatus.ACTIVE,
            title=title,
            assigned_by_user_id=assigned_by_user_id,
            author_label=author_label,
            source_program_id=source_program_id,
            source_author_user_id=source_author_user_id,
            days=list(detached.days),
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
        detached = document.without_slot_ids()
        return cls(
            user_id=user_id,
            program_type=detached.program_type,
            status=ProgramStatus.DRAFT,
            title=title or "Черновик программы",
            author_label=author_label,
            source_program_id=source_program_id,
            source_author_user_id=source_author_user_id,
            days=list(detached.days),
            created_at=moment,
        )

    def to_document(self) -> WorkoutDocument:
        return WorkoutDocument(
            program_type=self.program_type,
            days=list(self.days),
        )

    def display_title(self) -> str:
        localized = program_type_label(self.program_type)
        if not self.title:
            return localized
        # Older auto-titles used English enum values ("Full Body").
        english_auto = self.program_type.value.replace("_", " ").title()
        if self.title == english_auto:
            return localized
        return self.title

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

    @property
    def is_library_card(self) -> bool:
        return self.status in LIBRARY_CARD_STATUSES

    def _require_library_card(self) -> None:
        if not self.is_library_card:
            raise DomainError("only library cards (draft or published) can be changed here")

    def rename(self, title: str) -> None:
        self._require_library_card()
        self.title = normalize_library_title(title)

    def replace_document(self, document: WorkoutDocument) -> None:
        """Save an edited week back into a library card; the card keeps its status and code."""
        self._require_library_card()
        document.assert_approvable()
        detached = document.without_slot_ids()
        self.program_type = detached.program_type
        self.days = list(detached.days)

    def remove_from_library(self, *, now: datetime | None = None) -> None:
        """Soft delete: hide the card; copies already claimed by others stay untouched."""
        self._require_library_card()
        self.status = ProgramStatus.ARCHIVED
        self.distribution_code = None
        self.published_at = None
        self.archived_at = now or datetime.now(UTC)

    def template_day_for(self, day: WorkoutDay) -> WorkoutDay | None:
        """The program day a session day was copied from (same position and weekday)."""
        return next(
            (item for item in self.days if item.position == day.position and item.weekday == day.weekday),
            None,
        )

    def replace_slot_exercise(
        self,
        *,
        day_position: int,
        slot_position: int,
        exercise_id: UUID,
        weight_kg: Decimal | None,
    ) -> None:
        if self.status != ProgramStatus.ACTIVE:
            raise DomainError("only the active program can be changed from a workout")
        day = next((item for item in self.days if item.position == day_position), None)
        slot = next((item for item in day.slots if item.position == slot_position), None) if day else None
        if day is None or slot is None:
            raise DomainError("program slot not found")
        updated = slot.with_exercise(exercise_id).model_copy(update={"weight_kg": weight_kg, "technique_note": ""})
        slots = [updated if item.position == slot_position else item for item in day.slots]
        new_day = day.model_copy(update={"slots": slots})
        self.days = [new_day if item.position == day_position else item for item in self.days]

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
            days=list(self.to_document().without_slot_ids().days),
            created_at=moment,
        )
