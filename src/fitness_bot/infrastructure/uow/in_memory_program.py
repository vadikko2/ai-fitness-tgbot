from __future__ import annotations

from copy import deepcopy
from uuid import UUID, uuid4

from fitness_bot.domain.enums import ProgramStatus, ProposalStatus, SessionStatus
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay
from fitness_bot.domain.workout.program import Program
from fitness_bot.domain.workout.proposal import Proposal
from fitness_bot.domain.workout.session import Session
from fitness_bot.service.interfaces.uow import IProgramsRepository, IProposalsRepository, ISessionsRepository


def _ensure_slot_ids(day: WorkoutDay) -> WorkoutDay:
    slots: list[ExerciseSlot] = []
    for slot in day.slots:
        if slot.id is None:
            slots.append(slot.model_copy(update={"id": uuid4()}))
        else:
            slots.append(slot)
    return day.model_copy(update={"slots": slots})


class InMemoryProgramsRepository(IProgramsRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Program] = {}

    async def get_by_id(self, program_id: UUID) -> Program | None:
        program = self._by_id.get(program_id)
        return deepcopy(program) if program else None

    async def get_active_for_user(self, user_id: UUID) -> Program | None:
        for program in self._by_id.values():
            if program.user_id == user_id and program.status == ProgramStatus.ACTIVE:
                return deepcopy(program)
        return None

    async def add(self, program: Program) -> Program:
        stored = deepcopy(program)
        self._by_id[stored.id] = stored
        return deepcopy(stored)

    async def save(self, program: Program) -> Program:
        if program.id not in self._by_id:
            raise KeyError(program.id)
        stored = deepcopy(program)
        self._by_id[stored.id] = stored
        return deepcopy(stored)

    async def list_catalog_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Program]:
        items = [
            program
            for program in self._by_id.values()
            if program.user_id == user_id and program.status in {ProgramStatus.DRAFT, ProgramStatus.PUBLISHED}
        ]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return [deepcopy(item) for item in items[offset : offset + limit]]

    async def get_by_distribution_code(self, code: str) -> Program | None:
        normalized = code.strip().upper()
        for program in self._by_id.values():
            if program.distribution_code == normalized and program.status == ProgramStatus.PUBLISHED:
                return deepcopy(program)
        return None

    async def find_existing_claim(self, *, user_id: UUID, source_program_id: UUID) -> Program | None:
        matches = [
            program
            for program in self._by_id.values()
            if program.user_id == user_id
            and program.source_program_id == source_program_id
            and program.status in {ProgramStatus.DRAFT, ProgramStatus.PUBLISHED}
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: item.created_at, reverse=True)
        return deepcopy(matches[0])

    async def publish(self, program: Program) -> Program:
        program.publish()
        return await self.save(program)

    async def unpublish(self, program: Program) -> Program:
        program.unpublish()
        return await self.save(program)


class InMemoryProposalsRepository(IProposalsRepository):
    def __init__(self, programs: InMemoryProgramsRepository | None = None) -> None:
        self._by_id: dict[UUID, Proposal] = {}
        self._programs = programs

    async def get_by_id(self, proposal_id: UUID) -> Proposal | None:
        proposal = self._by_id.get(proposal_id)
        return deepcopy(proposal) if proposal else None

    async def get_pending_for_user(self, user_id: UUID) -> Proposal | None:
        for proposal in self._by_id.values():
            if proposal.user_id == user_id and proposal.status == ProposalStatus.PENDING:
                return deepcopy(proposal)
        return None

    async def save(self, proposal: Proposal) -> Proposal:
        stored = deepcopy(proposal)
        self._by_id[stored.id] = stored
        return deepcopy(stored)

    async def attach_days_to_program(self, proposal_id: UUID, program_id: UUID) -> None:
        proposal = self._by_id.get(proposal_id)
        if proposal is None or proposal.document is None or self._programs is None:
            return
        program = self._programs._by_id.get(program_id)
        if program is None:
            return
        program.days = deepcopy(proposal.document.days)
        self._programs._by_id[program_id] = program


class InMemorySessionsRepository(ISessionsRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Session] = {}

    async def get_by_id(self, session_id: UUID) -> Session | None:
        session = self._by_id.get(session_id)
        return deepcopy(session) if session else None

    async def get_open_for_user(self, user_id: UUID) -> Session | None:
        for session in self._by_id.values():
            if session.user_id == user_id and session.is_open:
                return deepcopy(session)
        return None

    async def list_completed_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Session]:
        items = [
            session
            for session in self._by_id.values()
            if session.user_id == user_id and session.status == SessionStatus.COMPLETED
        ]
        items.sort(key=lambda item: item.completed_at or item.started_at, reverse=True)
        return [deepcopy(item) for item in items[offset : offset + limit]]

    async def add(self, session: Session) -> Session:
        stored = deepcopy(session)
        stored.day = _ensure_slot_ids(stored.day)
        self._by_id[stored.id] = stored
        return deepcopy(stored)

    async def save(self, session: Session) -> Session:
        if session.id not in self._by_id:
            raise KeyError(session.id)
        previous = self._by_id[session.id]
        stored = deepcopy(session)
        by_position = {slot.position: slot.id for slot in previous.day.slots if slot.id is not None}
        slots = []
        for slot in stored.day.slots:
            if slot.id is not None:
                slots.append(slot)
            elif slot.position in by_position:
                slots.append(slot.model_copy(update={"id": by_position[slot.position]}))
            else:
                slots.append(slot.model_copy(update={"id": uuid4()}))
        stored.day = stored.day.model_copy(update={"slots": slots})
        self._by_id[stored.id] = stored
        return deepcopy(stored)

    async def delete(self, session_id: UUID) -> None:
        self._by_id.pop(session_id, None)
