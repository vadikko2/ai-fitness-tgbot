from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fitness_bot.domain.enums import (
    ProgramStatus,
    ProgramType,
    ProposalKind,
    ProposalStatus,
    TrainingStyle,
    WorkoutIntensity,
)
from fitness_bot.domain.workout.document import ExerciseSlot, SlotActual, WorkoutDay, WorkoutDocument
from fitness_bot.domain.workout.program import Program
from fitness_bot.domain.workout.proposal import Proposal
from fitness_bot.infrastructure.db.models import (
    ExerciseSlotRow,
    ProgramRow,
    ProposalRow,
    SlotActualRow,
    WorkoutDayRow,
)
from fitness_bot.service.interfaces.uow import IProgramsRepository, IProposalsRepository


def _actual_to_domain(row: SlotActualRow | None) -> SlotActual | None:
    if row is None:
        return None
    return SlotActual(
        sets=row.sets,
        reps=row.reps,
        duration_seconds=row.duration_seconds,
        weight_kg=row.weight_kg,
        note=row.note or "",
    )


def _slot_actual_or_none(row: ExerciseSlotRow) -> SlotActual | None:
    """Read actual without triggering async lazy IO (MissingGreenlet)."""
    state = sa_inspect(row)
    if "actual" in state.unloaded:
        return None
    return _actual_to_domain(row.actual)


def _slots_to_domain(rows: list[ExerciseSlotRow]) -> list[ExerciseSlot]:
    return [
        ExerciseSlot(
            id=row.id,
            position=row.position,
            exercise_id=row.exercise_id,
            custom_request=row.custom_request,
            muscle_group=row.muscle_group,
            sets=row.sets,
            reps=row.reps,
            duration_seconds=row.duration_seconds,
            weight_kg=row.weight_kg,
            rest_seconds=row.rest_seconds,
            rpe=row.rpe,
            technique_note=row.technique_note or "",
            actual=_slot_actual_or_none(row),
        )
        for row in sorted(rows, key=lambda item: item.position)
    ]


def _days_to_domain(rows: list[WorkoutDayRow]) -> list[WorkoutDay]:
    return [
        WorkoutDay(
            weekday=row.weekday,
            title=row.title,
            position=row.position,
            intensity=WorkoutIntensity(row.intensity or WorkoutIntensity.MEDIUM.value),
            training_style=TrainingStyle(row.training_style or TrainingStyle.CLASSIC.value),
            warmup=row.warmup or "",
            cooldown=row.cooldown or "",
            slots=_slots_to_domain(list(row.slots)),
        )
        for row in sorted(rows, key=lambda item: item.position)
    ]


def _build_day_rows(
    *,
    days: list[WorkoutDay],
    program_id: UUID | None,
    proposal_id: UUID | None,
    session_id: UUID | None = None,
) -> list[WorkoutDayRow]:
    rows: list[WorkoutDayRow] = []
    for day in days:
        slot_rows: list[ExerciseSlotRow] = []
        for slot in day.slots:
            slot_kwargs = {
                "position": slot.position,
                "exercise_id": slot.exercise_id,
                "custom_request": slot.custom_request,
                "muscle_group": slot.muscle_group,
                "sets": slot.sets,
                "reps": slot.reps,
                "duration_seconds": slot.duration_seconds,
                "weight_kg": slot.weight_kg,
                "rest_seconds": slot.rest_seconds,
                "rpe": slot.rpe,
                "technique_note": slot.technique_note,
            }
            if slot.id is not None:
                slot_kwargs["id"] = slot.id
            slot_row = ExerciseSlotRow(**slot_kwargs)
            if slot.actual is not None:
                slot_row.actual = SlotActualRow(
                    sets=slot.actual.sets,
                    reps=slot.actual.reps,
                    duration_seconds=slot.actual.duration_seconds,
                    weight_kg=slot.actual.weight_kg,
                    note=slot.actual.note,
                )
            else:
                # Mark relationship loaded so later domain mapping does not lazy-IO.
                slot_row.actual = None
            slot_rows.append(slot_row)
        rows.append(
            WorkoutDayRow(
                program_id=program_id,
                proposal_id=proposal_id,
                session_id=session_id,
                weekday=day.weekday,
                title=day.title,
                position=day.position,
                intensity=day.intensity.value,
                training_style=day.training_style.value,
                warmup=day.warmup,
                cooldown=day.cooldown,
                slots=slot_rows,
            ),
        )
    return rows


def _replace_days(
    *,
    existing: list[WorkoutDayRow],
    days: list[WorkoutDay],
    program_id: UUID | None,
    proposal_id: UUID | None,
    session_id: UUID | None = None,
) -> list[WorkoutDayRow]:
    """Replace day rows in-memory. Caller must flush DELETEs before INSERTs when
    unique (owner_id, position) constraints apply — see proposals.save."""
    existing.clear()
    rows = _build_day_rows(
        days=days,
        program_id=program_id,
        proposal_id=proposal_id,
        session_id=session_id,
    )
    existing.extend(rows)
    return rows


async def _replace_days_flush(
    session: AsyncSession,
    *,
    existing: list[WorkoutDayRow],
    days: list[WorkoutDay],
    program_id: UUID | None,
    proposal_id: UUID | None,
    session_id: UUID | None = None,
) -> list[WorkoutDayRow]:
    """Clear + flush deletes, then insert, avoiding UniqueViolation on position."""
    existing.clear()
    await session.flush()
    rows = _build_day_rows(
        days=days,
        program_id=program_id,
        proposal_id=proposal_id,
        session_id=session_id,
    )
    existing.extend(rows)
    return rows


def program_to_domain(row: ProgramRow) -> Program:
    return Program(
        id=row.id,
        user_id=row.user_id,
        program_type=ProgramType(row.program_type),
        status=ProgramStatus(row.status),
        title=row.title,
        distribution_code=row.distribution_code,
        published_at=row.published_at,
        source_program_id=row.source_program_id,
        source_author_user_id=row.source_author_user_id,
        assigned_by_user_id=row.assigned_by_user_id,
        author_label=row.author_label,
        days=_days_to_domain(list(row.days)),
        created_at=row.created_at,
        activated_at=row.activated_at,
        archived_at=row.archived_at,
    )


def proposal_to_domain(row: ProposalRow, *, reply: str = "") -> Proposal:
    document: WorkoutDocument | None = None
    if row.days:
        program_type = ProgramType(row.program_type) if row.program_type else ProgramType.FULL_BODY
        document = WorkoutDocument(
            program_type=program_type,
            days=_days_to_domain(list(row.days)),
        )
    return Proposal(
        id=row.id,
        user_id=row.user_id,
        kind=ProposalKind(row.kind),
        status=ProposalStatus(row.status),
        program_type=ProgramType(row.program_type) if row.program_type else None,
        base_program_id=row.base_program_id,
        base_session_id=row.base_session_id,
        document=document,
        reply=reply,
        created_at=row.created_at,
    )


class SqlAlchemyProgramsRepository(IProgramsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, program_id: UUID) -> Program | None:
        result = await self._session.execute(
            select(ProgramRow)
            .where(ProgramRow.id == program_id)
            .options(
                selectinload(ProgramRow.days).selectinload(WorkoutDayRow.slots).selectinload(ExerciseSlotRow.actual),
            ),
        )
        row = result.scalar_one_or_none()
        return program_to_domain(row) if row else None

    async def get_active_for_user(self, user_id: UUID) -> Program | None:
        result = await self._session.execute(
            select(ProgramRow)
            .where(ProgramRow.user_id == user_id, ProgramRow.status == ProgramStatus.ACTIVE.value)
            .options(
                selectinload(ProgramRow.days).selectinload(WorkoutDayRow.slots).selectinload(ExerciseSlotRow.actual),
            ),
        )
        row = result.scalar_one_or_none()
        return program_to_domain(row) if row else None

    async def add(self, program: Program) -> Program:
        row = ProgramRow(
            id=program.id,
            user_id=program.user_id,
            program_type=program.program_type.value,
            status=program.status.value,
            title=program.title,
            distribution_code=program.distribution_code,
            published_at=program.published_at,
            source_program_id=program.source_program_id,
            source_author_user_id=program.source_author_user_id,
            assigned_by_user_id=program.assigned_by_user_id,
            author_label=program.author_label,
            created_at=program.created_at,
            activated_at=program.activated_at,
            archived_at=program.archived_at,
            days=[],
        )
        # Days are attached from the proposal on approve; keep empty here unless provided.
        if program.days:
            _replace_days(existing=row.days, days=program.days, program_id=program.id, proposal_id=None)
        self._session.add(row)
        await self._session.flush()
        return program_to_domain(row)

    async def save(self, program: Program) -> Program:
        result = await self._session.execute(
            select(ProgramRow)
            .where(ProgramRow.id == program.id)
            .options(
                selectinload(ProgramRow.days).selectinload(WorkoutDayRow.slots).selectinload(ExerciseSlotRow.actual),
            ),
        )
        row = result.scalar_one()
        row.program_type = program.program_type.value
        row.status = program.status.value
        row.title = program.title
        row.distribution_code = program.distribution_code
        row.published_at = program.published_at
        row.source_program_id = program.source_program_id
        row.source_author_user_id = program.source_author_user_id
        row.assigned_by_user_id = program.assigned_by_user_id
        row.author_label = program.author_label
        row.activated_at = program.activated_at
        row.archived_at = program.archived_at
        if program.days:
            await _replace_days_flush(
                self._session,
                existing=row.days,
                days=program.days,
                program_id=program.id,
                proposal_id=None,
            )
        await self._session.flush()
        return program_to_domain(row)

    async def list_catalog_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Program]:
        result = await self._session.execute(
            select(ProgramRow)
            .where(
                ProgramRow.user_id == user_id,
                ProgramRow.status.in_([ProgramStatus.DRAFT.value, ProgramStatus.PUBLISHED.value]),
            )
            .order_by(ProgramRow.created_at.desc())
            .offset(offset)
            .limit(limit)
            .options(
                selectinload(ProgramRow.days).selectinload(WorkoutDayRow.slots).selectinload(ExerciseSlotRow.actual),
            ),
        )
        return [program_to_domain(row) for row in result.scalars().all()]

    async def get_by_distribution_code(self, code: str) -> Program | None:
        normalized = code.strip().upper()
        result = await self._session.execute(
            select(ProgramRow)
            .where(
                ProgramRow.distribution_code == normalized,
                ProgramRow.status == ProgramStatus.PUBLISHED.value,
            )
            .options(
                selectinload(ProgramRow.days).selectinload(WorkoutDayRow.slots).selectinload(ExerciseSlotRow.actual),
            ),
        )
        row = result.scalar_one_or_none()
        return program_to_domain(row) if row else None

    async def find_existing_claim(self, *, user_id: UUID, source_program_id: UUID) -> Program | None:
        result = await self._session.execute(
            select(ProgramRow)
            .where(
                ProgramRow.user_id == user_id,
                ProgramRow.source_program_id == source_program_id,
                ProgramRow.status.in_([ProgramStatus.DRAFT.value, ProgramStatus.PUBLISHED.value]),
            )
            .order_by(ProgramRow.created_at.desc())
            .limit(1)
            .options(
                selectinload(ProgramRow.days).selectinload(WorkoutDayRow.slots).selectinload(ExerciseSlotRow.actual),
            ),
        )
        row = result.scalar_one_or_none()
        return program_to_domain(row) if row else None

    async def publish(self, program: Program) -> Program:
        program.publish()
        return await self.save(program)

    async def unpublish(self, program: Program) -> Program:
        program.unpublish()
        return await self.save(program)


class SqlAlchemyProposalsRepository(IProposalsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, proposal_id: UUID) -> Proposal | None:
        result = await self._session.execute(
            select(ProposalRow)
            .where(ProposalRow.id == proposal_id)
            .options(
                selectinload(ProposalRow.days).selectinload(WorkoutDayRow.slots).selectinload(ExerciseSlotRow.actual),
            ),
        )
        row = result.scalar_one_or_none()
        return proposal_to_domain(row) if row else None

    async def get_pending_for_user(self, user_id: UUID) -> Proposal | None:
        result = await self._session.execute(
            select(ProposalRow)
            .where(ProposalRow.user_id == user_id, ProposalRow.status == ProposalStatus.PENDING.value)
            .options(
                selectinload(ProposalRow.days).selectinload(WorkoutDayRow.slots).selectinload(ExerciseSlotRow.actual),
            ),
        )
        row = result.scalar_one_or_none()
        return proposal_to_domain(row) if row else None

    async def save(self, proposal: Proposal) -> Proposal:
        result = await self._session.execute(
            select(ProposalRow)
            .where(ProposalRow.id == proposal.id)
            .options(
                selectinload(ProposalRow.days).selectinload(WorkoutDayRow.slots).selectinload(ExerciseSlotRow.actual),
            ),
        )
        row = result.scalar_one_or_none()
        if row is None:
            # Client-assigned UUID; keep transient until final flush so accessing
            # ``days`` does not trigger async lazy-load (MissingGreenlet).
            row = ProposalRow(
                id=proposal.id,
                user_id=proposal.user_id,
                kind=proposal.kind.value,
                status=proposal.status.value,
                program_type=proposal.program_type.value if proposal.program_type else None,
                base_program_id=proposal.base_program_id,
                base_session_id=proposal.base_session_id,
                created_at=proposal.created_at,
                days=[],
            )
            self._session.add(row)
        else:
            row.kind = proposal.kind.value
            row.status = proposal.status.value
            row.program_type = proposal.program_type.value if proposal.program_type else None
            row.base_program_id = proposal.base_program_id
            row.base_session_id = proposal.base_session_id

        if proposal.status == ProposalStatus.DISCARDED:
            # Keep rows orphaned-delete; do not re-insert from domain document.
            row.days.clear()
        elif proposal.document is not None:
            await _replace_days_flush(
                self._session,
                existing=row.days,
                days=proposal.document.days,
                program_id=None,
                proposal_id=proposal.id,
            )
        elif proposal.status != ProposalStatus.APPROVED:
            row.days.clear()
        await self._session.flush()
        # reply is domain-only (not stored); keep it on the mapped entity.
        return proposal_to_domain(row, reply=proposal.reply)

    async def attach_days_to_program(self, proposal_id: UUID, program_id: UUID) -> None:
        await self._session.execute(
            update(WorkoutDayRow)
            .where(WorkoutDayRow.proposal_id == proposal_id)
            .values(program_id=program_id, proposal_id=None),
        )
        await self._session.flush()
