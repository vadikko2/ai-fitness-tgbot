from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from fitness_bot.domain.enums import ProgramType, SessionStatus
from fitness_bot.domain.errors import DomainError, InvalidWorkoutDocument
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument


class Session(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    source_day_id: UUID | None = None
    status: SessionStatus = SessionStatus.IN_PROGRESS
    program_type: ProgramType
    day: WorkoutDay
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @classmethod
    def from_template_day(
        cls,
        *,
        user_id: UUID,
        program_type: ProgramType,
        day: WorkoutDay,
        source_day_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Session:
        moment = now or datetime.now(UTC)
        copied = day.model_copy(deep=True)
        # Fresh session identity: do not reuse template/proposal slot PKs (or prior actuals).
        cleared_slots = [slot.model_copy(update={"actual": None, "id": uuid4()}) for slot in copied.slots]
        copied = copied.model_copy(update={"slots": cleared_slots})
        return cls(
            user_id=user_id,
            source_day_id=source_day_id,
            status=SessionStatus.IN_PROGRESS,
            program_type=program_type,
            day=copied,
            started_at=moment,
        )

    @classmethod
    def from_document(
        cls,
        *,
        user_id: UUID,
        document: WorkoutDocument,
        source_day_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Session:
        if len(document.days) != 1:
            raise InvalidWorkoutDocument("session requires exactly one day")
        return cls.from_template_day(
            user_id=user_id,
            program_type=document.program_type,
            day=document.days[0],
            source_day_id=source_day_id,
            now=now,
        )

    def to_document(self) -> WorkoutDocument:
        return WorkoutDocument(program_type=self.program_type, days=[self.day])

    def apply_document(self, document: WorkoutDocument) -> None:
        if self.status not in {SessionStatus.IN_PROGRESS, SessionStatus.PENDING_COMPLETION}:
            raise DomainError("only an open session can be edited")
        if len(document.days) != 1:
            raise InvalidWorkoutDocument("session edit requires exactly one day")
        self.day = self._preserve_slot_ids(document.days[0])
        self.program_type = document.program_type

    def slot_at(self, position: int) -> ExerciseSlot:
        for slot in self.day.slots:
            if slot.position == position:
                return slot
        raise InvalidWorkoutDocument(f"slot position={position} not found")

    def confirm_slot_as_planned(self, position: int) -> ExerciseSlot:
        if self.status != SessionStatus.IN_PROGRESS:
            raise DomainError("slot can be confirmed only while session is in_progress")
        slot = self.slot_at(position)
        updated = slot.with_actual(slot.planned_actual())
        self._replace_slot(updated)
        return updated

    def clear_slot_actual(self, position: int) -> ExerciseSlot:
        """Drop a logged set so the exercise is no longer confirmed."""
        if self.status != SessionStatus.IN_PROGRESS:
            raise DomainError("slot confirmation can be undone only while session is in_progress")
        slot = self.slot_at(position)
        if slot.actual is None:
            raise DomainError("slot is not confirmed")
        updated = slot.model_copy(update={"actual": None})
        self._replace_slot(updated)
        return updated

    def apply_slot_actual(self, position: int, actual: SlotActual) -> ExerciseSlot:
        if self.status not in {SessionStatus.IN_PROGRESS, SessionStatus.PENDING_COMPLETION}:
            raise DomainError("only an open session can record slot actual")
        updated = self.slot_at(position).with_actual(actual)
        self._replace_slot(updated)
        return updated

    def swap_slot_exercise(self, position: int, exercise_id: UUID, *, weight_kg: Decimal | None) -> ExerciseSlot:
        """Replace the exercise of a not-yet-logged slot; sets, reps and rest stay as planned."""
        if self.status != SessionStatus.IN_PROGRESS:
            raise DomainError("exercise can be swapped only while session is in_progress")
        slot = self.slot_at(position)
        if slot.actual is not None:
            raise DomainError("exercise with logged sets cannot be swapped")
        updated = slot.with_exercise(exercise_id).model_copy(update={"weight_kg": weight_kg, "technique_note": ""})
        self._replace_slot(updated)
        return updated

    def fill_all_actuals_from_plan(self) -> None:
        slots = [slot.with_actual(slot.planned_actual()) for slot in self.day.slots]
        self.day = self.day.model_copy(update={"slots": slots})

    def clear_actuals(self) -> None:
        if self.status not in {SessionStatus.IN_PROGRESS, SessionStatus.PENDING_COMPLETION}:
            raise DomainError("only an open session can clear actuals")
        slots = [slot.model_copy(update={"actual": None}) for slot in self.day.slots]
        self.day = self.day.model_copy(update={"slots": slots})
        self.status = SessionStatus.IN_PROGRESS

    def _preserve_slot_ids(self, day: WorkoutDay) -> WorkoutDay:
        by_position = {slot.position: slot.id for slot in self.day.slots if slot.id is not None}
        slots = [
            slot if slot.id is not None else slot.model_copy(update={"id": by_position.get(slot.position)})
            for slot in day.slots
        ]
        return day.model_copy(update={"slots": slots})

    def begin_completion(self) -> None:
        if self.status != SessionStatus.IN_PROGRESS:
            raise DomainError("completion can start only from in_progress")
        if not self.day.slots:
            raise DomainError("session has no slots to complete")
        self.fill_all_actuals_from_plan()
        self.status = SessionStatus.PENDING_COMPLETION

    def finalize(self, *, now: datetime | None = None) -> None:
        if self.status not in {SessionStatus.IN_PROGRESS, SessionStatus.PENDING_COMPLETION}:
            raise DomainError("only an open session can be finalized")
        self.status = SessionStatus.COMPLETED
        self.completed_at = now or datetime.now(UTC)

    def _replace_slot(self, updated: ExerciseSlot) -> None:
        slots = [updated if slot.position == updated.position else slot for slot in self.day.slots]
        self.day = self.day.model_copy(update={"slots": slots})

    @property
    def is_open(self) -> bool:
        return self.status in {SessionStatus.IN_PROGRESS, SessionStatus.PENDING_COMPLETION}
