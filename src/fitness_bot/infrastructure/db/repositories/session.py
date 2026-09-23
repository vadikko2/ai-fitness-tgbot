from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fitness_bot.domain.enums import ProgramType, SessionStatus
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay
from fitness_bot.domain.workout.session import Session
from fitness_bot.infrastructure.db.models import (
    ExerciseSlotRow,
    ProgramRow,
    ProposalRow,
    SessionRow,
    SlotActualRow,
    UserRow,
    WorkoutDayRow,
)
from fitness_bot.infrastructure.db.repositories.program import _days_to_domain
from fitness_bot.service.interfaces.uow import ISessionsRepository


def _session_load_options():
    return selectinload(SessionRow.day).selectinload(WorkoutDayRow.slots).selectinload(ExerciseSlotRow.actual)


def _apply_actual(slot_row: ExerciseSlotRow, actual: SlotActual | None) -> None:
    if actual is None:
        # Assign None explicitly so the relationship is marked loaded (no async lazy IO).
        slot_row.actual = None
        return
    state = sa_inspect(slot_row)
    existing = None if "actual" in state.unloaded else slot_row.actual
    if existing is None:
        slot_row.actual = SlotActualRow(
            sets=actual.sets,
            reps=actual.reps,
            duration_seconds=actual.duration_seconds,
            weight_kg=actual.weight_kg,
            note=actual.note,
        )
        return
    existing.sets = actual.sets
    existing.reps = actual.reps
    existing.duration_seconds = actual.duration_seconds
    existing.weight_kg = actual.weight_kg
    existing.note = actual.note


def _apply_slot_fields(slot_row: ExerciseSlotRow, slot: ExerciseSlot) -> None:
    slot_row.position = slot.position
    slot_row.exercise_id = slot.exercise_id
    slot_row.custom_request = slot.custom_request
    slot_row.muscle_group = slot.muscle_group
    slot_row.sets = slot.sets
    slot_row.reps = slot.reps
    slot_row.duration_seconds = slot.duration_seconds
    slot_row.weight_kg = slot.weight_kg
    slot_row.rest_seconds = slot.rest_seconds
    slot_row.rpe = slot.rpe
    slot_row.technique_note = slot.technique_note
    _apply_actual(slot_row, slot.actual)


def _new_slot_row(slot: ExerciseSlot) -> ExerciseSlotRow:
    slot_row = ExerciseSlotRow(
        id=slot.id or uuid4(),
        position=slot.position,
        exercise_id=slot.exercise_id,
        custom_request=slot.custom_request,
        muscle_group=slot.muscle_group,
        sets=slot.sets,
        reps=slot.reps,
        duration_seconds=slot.duration_seconds,
        weight_kg=slot.weight_kg,
        rest_seconds=slot.rest_seconds,
        rpe=slot.rpe,
        technique_note=slot.technique_note,
    )
    _apply_actual(slot_row, slot.actual)
    return slot_row


class SqlAlchemySessionsRepository(ISessionsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _program_type_for_user(self, user_id: UUID) -> ProgramType:
        result = await self._session.execute(
            select(ProgramRow.program_type)
            .join(UserRow, UserRow.active_program_id == ProgramRow.id)
            .where(UserRow.id == user_id),
        )
        value = result.scalar_one_or_none()
        if value is None:
            return ProgramType.FULL_BODY
        return ProgramType(value)

    @staticmethod
    def _day_or_none(row: SessionRow) -> WorkoutDayRow | None:
        """Read day without triggering async lazy IO (MissingGreenlet)."""
        state = sa_inspect(row)
        if "day" in state.unloaded:
            return None
        return row.day

    def _to_domain(self, row: SessionRow, *, program_type: ProgramType) -> Session:
        day_row = self._day_or_none(row)
        days = _days_to_domain([day_row] if day_row is not None else [])
        day = days[0] if days else WorkoutDay(title="Тренировка", position=1, slots=[])
        return Session(
            id=row.id,
            user_id=row.user_id,
            source_day_id=row.source_day_id,
            status=SessionStatus(row.status),
            program_type=program_type,
            day=day,
            started_at=row.started_at,
            completed_at=row.completed_at,
        )

    async def get_by_id(self, session_id: UUID) -> Session | None:
        result = await self._session.execute(
            select(SessionRow).where(SessionRow.id == session_id).options(_session_load_options()),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        program_type = await self._program_type_for_user(row.user_id)
        return self._to_domain(row, program_type=program_type)

    async def get_open_for_user(self, user_id: UUID) -> Session | None:
        result = await self._session.execute(
            select(SessionRow)
            .where(
                SessionRow.user_id == user_id,
                SessionRow.status.in_(
                    [SessionStatus.IN_PROGRESS.value, SessionStatus.PENDING_COMPLETION.value],
                ),
            )
            .options(_session_load_options()),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        program_type = await self._program_type_for_user(row.user_id)
        return self._to_domain(row, program_type=program_type)

    async def list_completed_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Session]:
        result = await self._session.execute(
            select(SessionRow)
            .where(
                SessionRow.user_id == user_id,
                SessionRow.status == SessionStatus.COMPLETED.value,
            )
            .options(_session_load_options())
            .order_by(SessionRow.completed_at.desc())
            .offset(offset)
            .limit(limit),
        )
        rows = result.scalars().all()
        program_type = await self._program_type_for_user(user_id)
        return [self._to_domain(row, program_type=program_type) for row in rows]

    async def _sync_day(self, row: SessionRow, day: WorkoutDay) -> None:
        day_row = self._day_or_none(row)
        if day_row is None:
            row.day = WorkoutDayRow(
                session_id=row.id,
                weekday=day.weekday,
                title=day.title,
                position=day.position,
                intensity=day.intensity.value,
                training_style=day.training_style.value,
                warmup=day.warmup,
                cooldown=day.cooldown,
                slots=[_new_slot_row(slot) for slot in day.slots],
            )
            return

        day_row.weekday = day.weekday
        day_row.title = day.title
        day_row.position = day.position
        day_row.intensity = day.intensity.value
        day_row.training_style = day.training_style.value
        day_row.warmup = day.warmup
        day_row.cooldown = day.cooldown
        existing_by_pos = {slot.position: slot for slot in list(day_row.slots)}
        new_positions = {slot.position for slot in day.slots}
        for position, slot_row in list(existing_by_pos.items()):
            if position not in new_positions:
                day_row.slots.remove(slot_row)
                await self._session.delete(slot_row)
        for slot in day.slots:
            existing = existing_by_pos.get(slot.position)
            if existing is None:
                day_row.slots.append(_new_slot_row(slot))
                continue
            if slot.id is not None and existing.id != slot.id:
                # Keep the persisted id so technique_videos stay attached.
                pass
            _apply_slot_fields(existing, slot)

    async def add(self, session: Session) -> Session:
        row = SessionRow(
            id=session.id,
            user_id=session.user_id,
            source_day_id=session.source_day_id,
            status=session.status.value,
            started_at=session.started_at,
            completed_at=session.completed_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._sync_day(row, session.day)
        await self._session.flush()
        return self._to_domain(row, program_type=session.program_type)

    async def save(self, session: Session) -> Session:
        result = await self._session.execute(
            select(SessionRow).where(SessionRow.id == session.id).options(_session_load_options()),
        )
        row = result.scalar_one()
        row.status = session.status.value
        row.source_day_id = session.source_day_id
        row.completed_at = session.completed_at
        await self._sync_day(row, session.day)
        await self._session.flush()
        return self._to_domain(row, program_type=session.program_type)

    async def delete(self, session_id: UUID) -> None:
        await self._session.execute(
            update(ProposalRow).where(ProposalRow.base_session_id == session_id).values(base_session_id=None),
        )
        result = await self._session.execute(
            select(SessionRow).where(SessionRow.id == session_id).options(_session_load_options()),
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        await self._session.delete(row)
        await self._session.flush()
