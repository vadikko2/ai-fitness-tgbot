from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fitness_bot.domain.enums import ProgramStatus, ProgramType, ProposalStatus, SessionStatus
from fitness_bot.domain.users.user import local_calendar_date
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay, WorkoutDocument
from fitness_bot.domain.workout.program import Program
from fitness_bot.domain.workout.proposal import Proposal
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.body import RecordWellbeingCommandHandler
from fitness_bot.service.handlers.commands.session import (
    FinalizeSessionCommandHandler,
    StartTodayWorkoutCommandHandler,
)
from fitness_bot.service.handlers.commands.users import EnsureUserCommandHandler
from fitness_bot.service.handlers.queries.session import GetTodayWorkoutQueryHandler
from fitness_bot.service.models.commands.body import RecordWellbeingCommand
from fitness_bot.service.models.commands.session import FinalizeSessionCommand, StartTodayWorkoutCommand
from fitness_bot.service.models.commands.users import EnsureUserCommand
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery

TG = 11


def _today_weekday() -> int:
    return local_calendar_date(now=datetime.now(UTC), timezone_offset=None).isoweekday()


def _shift(weekday: int, days: int) -> int:
    return (weekday - 1 + days) % 7 + 1


def _day(weekday: int, title: str, position: int) -> WorkoutDay:
    return WorkoutDay(
        weekday=weekday,
        title=title,
        position=position,
        slots=[
            ExerciseSlot(position=1, exercise_id=uuid4(), sets=3, reps=8, rest_seconds=90, rpe=7),
            ExerciseSlot(position=2, exercise_id=uuid4(), sets=3, reps=10, rest_seconds=90, rpe=7),
        ],
    )


async def _seed(uow: InMemoryUow, weekdays: list[int] | None) -> Program | None:
    await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=TG, chat_id=110))
    if weekdays is None:
        return None
    program = Program(
        user_id=uuid4(),
        program_type=ProgramType.FULL_BODY,
        status=ProgramStatus.ACTIVE,
        days=[_day(weekday, f"День {weekday}", index) for index, weekday in enumerate(weekdays, start=1)],
        activated_at=datetime.now(UTC) - timedelta(days=1),
    )
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None
        program = program.model_copy(update={"user_id": user.id})
        await repos.programs.add(program)
        user.active_program_id = program.id
        await repos.users.save(user)
    return program


async def _go(uow: InMemoryUow, weekday: int | None = None):
    return await StartTodayWorkoutCommandHandler(uow).handle(
        StartTodayWorkoutCommand(telegram_user_id=TG, weekday=weekday),
    )


async def test_one_tap_without_program_guides_to_program() -> None:
    uow = InMemoryUow()
    await _seed(uow, None)
    result = await _go(uow)
    assert result.outcome == "no_program"


async def test_one_tap_starts_today_then_resumes() -> None:
    uow = InMemoryUow()
    today = _today_weekday()
    await _seed(uow, [today, _shift(today, 2)])

    started = await _go(uow)
    assert started.outcome == "started"
    assert started.session_status == SessionStatus.IN_PROGRESS
    assert started.document is not None
    assert started.document.days[0].title == f"День {today}"
    assert started.has_unapplied_wellbeing is False

    resumed = await _go(uow)
    assert resumed.outcome == "resumed"
    assert resumed.session_id == started.session_id

    view = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=TG))
    assert view.screen == "session"


async def test_one_tap_with_fresh_wellbeing_starts_and_flags_banner() -> None:
    uow = InMemoryUow()
    today = _today_weekday()
    program = await _seed(uow, [today])
    assert program is not None
    await RecordWellbeingCommandHandler(uow).handle(RecordWellbeingCommand(telegram_user_id=TG, text="болит колено"))
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None
        stale = Proposal.new_next_session(
            user_id=user.id,
            document=WorkoutDocument(program_type=ProgramType.FULL_BODY, days=[program.days[0]]),
            base_program_id=program.id,
        )
        await repos.proposals.save(stale)
        user.pending_proposal_id = stale.id
        await repos.users.save(user)

    result = await _go(uow)
    assert result.outcome == "started"
    assert result.has_unapplied_wellbeing is True
    assert result.wellbeing_note == "болит колено"
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None and user.pending_proposal_id is None
        proposal = await repos.proposals.get_by_id(stale.id)
        assert proposal is not None and proposal.status == ProposalStatus.DISCARDED


async def test_one_tap_already_done_offers_next_open_day() -> None:
    uow = InMemoryUow()
    today = _today_weekday()
    other = _shift(today, 2)
    await _seed(uow, [today, other])
    await _go(uow)
    await FinalizeSessionCommandHandler(uow).handle(FinalizeSessionCommand(telegram_user_id=TG))

    result = await _go(uow)
    assert result.outcome == "already_done"
    assert result.weekday == today
    assert result.alternative_weekday == other
    assert result.completed_count == 1


async def test_one_tap_on_rest_day_offers_and_starts_nearest_open_day() -> None:
    uow = InMemoryUow()
    today = _today_weekday()
    first, second = _shift(today, 1), _shift(today, 3)
    await _seed(uow, [second, first])

    rest = await _go(uow)
    assert rest.outcome == "rest"
    assert rest.alternative_weekday == first
    assert rest.alternative_title == f"День {first}"
    view = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=TG))
    assert view.screen == "rest" and view.alternative_weekday == first

    started = await _go(uow, weekday=first)
    assert started.outcome == "started"
    assert started.document is not None and started.document.days[0].weekday == first
    await FinalizeSessionCommandHandler(uow).handle(FinalizeSessionCommand(telegram_user_id=TG))

    # The off-day workout counts as that program day, so the next offer moves on.
    rest_again = await _go(uow)
    assert rest_again.outcome == "rest"
    assert rest_again.alternative_weekday == second
    assert rest_again.completed_count == 1
