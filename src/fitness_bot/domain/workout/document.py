from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fitness_bot.domain.enums import ProgramType, TrainingStyle, WorkoutIntensity
from fitness_bot.domain.errors import EmptyProgramWeek, InvalidWorkoutDocument, UnresolvedExercises


class SlotActual(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    sets: int
    reps: int | None = None
    duration_seconds: int | None = None
    weight_kg: Decimal | None = None
    note: str = ""

    @model_validator(mode="after")
    def _reps_xor_duration(self) -> SlotActual:
        has_reps = self.reps is not None
        has_duration = self.duration_seconds is not None
        if has_reps == has_duration:
            raise InvalidWorkoutDocument("actual must have either reps or duration_seconds")
        if self.sets <= 0:
            raise InvalidWorkoutDocument("actual.sets must be positive")
        if self.reps is not None and self.reps <= 0:
            raise InvalidWorkoutDocument("actual.reps must be positive")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise InvalidWorkoutDocument("actual.duration_seconds must be positive")
        if self.weight_kg is not None and self.weight_kg <= 0:
            raise InvalidWorkoutDocument("actual.weight_kg must be positive")
        return self


class ExerciseSlot(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: UUID | None = None
    position: int
    exercise_id: UUID | None = None
    custom_request: str | None = None
    muscle_group: str | None = None
    sets: int
    reps: int | None = None
    duration_seconds: int | None = None
    weight_kg: Decimal | None = Field(
        default=None,
        description=(
            "Planned working weight in kilograms for loaded exercises "
            "(machines, free weights, cables). Null only for bodyweight "
            "or duration-based slots."
        ),
    )
    rest_seconds: int
    rpe: int
    technique_note: str = ""
    actual: SlotActual | None = None

    @model_validator(mode="after")
    def _invariants(self) -> ExerciseSlot:
        if self.position <= 0:
            raise InvalidWorkoutDocument("slot position must be positive")
        if self.sets <= 0:
            raise InvalidWorkoutDocument("sets must be positive")
        if self.rest_seconds <= 0:
            raise InvalidWorkoutDocument("rest_seconds must be positive")
        if self.rpe < 1 or self.rpe > 10:
            raise InvalidWorkoutDocument("rpe must be between 1 and 10")
        has_reps = self.reps is not None
        has_duration = self.duration_seconds is not None
        if has_reps == has_duration:
            raise InvalidWorkoutDocument("slot must have either reps or duration_seconds")
        if self.reps is not None and self.reps <= 0:
            raise InvalidWorkoutDocument("reps must be positive")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise InvalidWorkoutDocument("duration_seconds must be positive")
        if self.weight_kg is not None and self.weight_kg <= 0:
            raise InvalidWorkoutDocument("weight_kg must be positive")
        if self.exercise_id is None:
            if not (self.custom_request and self.muscle_group):
                raise InvalidWorkoutDocument(
                    "unresolved slot requires custom_request and muscle_group",
                )
        return self

    @property
    def is_resolved(self) -> bool:
        return self.exercise_id is not None

    def with_exercise(self, exercise_id: UUID) -> ExerciseSlot:
        return self.model_copy(
            update={
                "exercise_id": exercise_id,
                "custom_request": None,
                "muscle_group": None,
            },
        )

    def planned_actual(self) -> SlotActual:
        return SlotActual(
            sets=self.sets,
            reps=self.reps,
            duration_seconds=self.duration_seconds,
            weight_kg=self.weight_kg,
            note="",
        )

    def with_actual(self, actual: SlotActual) -> ExerciseSlot:
        return self.model_copy(update={"actual": actual})


class WorkoutDay(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    weekday: int | None = None
    title: str
    position: int
    intensity: WorkoutIntensity = WorkoutIntensity.MEDIUM
    training_style: TrainingStyle = TrainingStyle.CLASSIC
    warmup: str = ""
    cooldown: str = ""
    slots: list[ExerciseSlot] = Field(default_factory=list)

    @model_validator(mode="after")
    def _invariants(self) -> WorkoutDay:
        if self.position <= 0:
            raise InvalidWorkoutDocument("day position must be positive")
        if not self.title.strip():
            raise InvalidWorkoutDocument("day title must not be empty")
        if self.weekday is not None and (self.weekday < 1 or self.weekday > 7):
            raise InvalidWorkoutDocument("weekday must be between 1 and 7")
        positions = [slot.position for slot in self.slots]
        if len(positions) != len(set(positions)):
            raise InvalidWorkoutDocument("slot positions within a day must be unique")
        return self


class WorkoutDocument(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    program_type: ProgramType
    days: list[WorkoutDay] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_day_positions(self) -> WorkoutDocument:
        positions = [day.position for day in self.days]
        if len(positions) != len(set(positions)):
            raise InvalidWorkoutDocument("day positions must be unique")
        return self

    def unresolved_slots(self) -> list[ExerciseSlot]:
        return [slot for day in self.days for slot in day.slots if not slot.is_resolved]

    def without_slot_ids(self) -> WorkoutDocument:
        """Detach from persisted slot rows so a clone can be inserted under a new owner.

        Programs, proposals, and sessions share the ``exercise_slots`` PK space.
        Cloning a document that still carries source slot UUIDs causes UniqueViolation
        on INSERT (e.g. coach live-edit of a client's active program).
        """
        return self.model_copy(
            update={
                "days": [
                    day.model_copy(
                        update={
                            "slots": [slot.model_copy(update={"id": None}) for slot in day.slots],
                        },
                    )
                    for day in self.days
                ],
            },
        )

    def assert_day_count(self, days_per_week: int) -> None:
        if len(self.days) != days_per_week:
            raise InvalidWorkoutDocument(
                f"day count must equal days_per_week ({days_per_week}), got {len(self.days)}",
            )

    def assert_schedule_complete(self, *, days_per_week: int | None = None) -> None:
        """Require every day to have a unique ISO weekday; optionally match days_per_week."""
        if not self.days:
            raise InvalidWorkoutDocument("schedule requires at least one day")
        weekdays: list[int] = []
        for day in self.days:
            if day.weekday is None:
                raise InvalidWorkoutDocument("each day must have weekday (1-7)")
            weekdays.append(day.weekday)
        if len(weekdays) != len(set(weekdays)):
            raise InvalidWorkoutDocument("weekdays must be unique across days")
        if days_per_week is not None:
            self.assert_day_count(days_per_week)

    def assert_catalog_ids(self, allowed: set[UUID]) -> None:
        for day in self.days:
            for slot in day.slots:
                if slot.exercise_id is not None and slot.exercise_id not in allowed:
                    raise InvalidWorkoutDocument(f"unknown exercise_id: {slot.exercise_id}")

    def assert_approvable(self, *, require_schedule: bool = False) -> None:
        if not self.days:
            raise EmptyProgramWeek("program week has no days")
        if not any(day.slots for day in self.days):
            raise EmptyProgramWeek("program week has no exercise slots")
        unresolved = self.unresolved_slots()
        if unresolved:
            raise UnresolvedExercises("all slots must have exercise_id before approve")
        if require_schedule:
            self.assert_schedule_complete()

    def replace_day(self, day: WorkoutDay) -> WorkoutDocument:
        days: list[WorkoutDay] = []
        found = False
        for existing in self.days:
            if existing.position != day.position:
                days.append(existing)
                continue
            days.append(day)
            found = True
        if not found:
            raise InvalidWorkoutDocument(f"day position={day.position} not found")
        return self.model_copy(update={"days": days})

    def select_exercise(self, *, day_position: int, slot_position: int, exercise_id: UUID) -> WorkoutDocument:
        days: list[WorkoutDay] = []
        found = False
        for day in self.days:
            if day.position != day_position:
                days.append(day)
                continue
            slots: list[ExerciseSlot] = []
            for slot in day.slots:
                if slot.position != slot_position:
                    slots.append(slot)
                    continue
                slots.append(slot.with_exercise(exercise_id))
                found = True
            days.append(day.model_copy(update={"slots": slots}))
        if not found:
            raise InvalidWorkoutDocument(
                f"slot day={day_position} position={slot_position} not found",
            )
        return self.model_copy(update={"days": days})

    def update_slot_planned(
        self,
        *,
        day_position: int,
        slot_position: int,
        weight_kg: Decimal | None,
        reps: int | None = None,
        duration_seconds: int | None = None,
    ) -> WorkoutDocument:
        """Update planned weight and reps/duration for one slot; keep sets/rest/rpe."""
        days: list[WorkoutDay] = []
        found = False
        for day in self.days:
            if day.position != day_position:
                days.append(day)
                continue
            slots: list[ExerciseSlot] = []
            for slot in day.slots:
                if slot.position != slot_position:
                    slots.append(slot)
                    continue
                updates: dict[str, object] = {"weight_kg": weight_kg}
                if slot.duration_seconds is not None:
                    if duration_seconds is None:
                        raise InvalidWorkoutDocument("duration_seconds is required for timed slot")
                    updates["duration_seconds"] = duration_seconds
                    updates["reps"] = None
                else:
                    if reps is None:
                        raise InvalidWorkoutDocument("reps is required for rep-based slot")
                    updates["reps"] = reps
                    updates["duration_seconds"] = None
                slots.append(slot.model_copy(update=updates))
                found = True
            days.append(day.model_copy(update={"slots": slots}))
        if not found:
            raise InvalidWorkoutDocument(
                f"slot day={day_position} position={slot_position} not found",
            )
        return self.model_copy(update={"days": days})


def unresolved_slot_refs(document: WorkoutDocument) -> list[tuple[int, int, str, str]]:
    """Return (day_position, slot_position, custom_request, muscle_group) for unresolved slots."""
    refs: list[tuple[int, int, str, str]] = []
    for day in document.days:
        for slot in day.slots:
            if slot.is_resolved:
                continue
            refs.append(
                (
                    day.position,
                    slot.position,
                    slot.custom_request or "",
                    slot.muscle_group or "",
                ),
            )
    return refs
