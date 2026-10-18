from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from fitness_bot.domain.enums import ExpectedInput, Goal, ProgramStatus, ProgramType
from fitness_bot.domain.errors import AgentUnavailable
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay
from fitness_bot.domain.workout.program import Program
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.body import RecordWellbeingCommandHandler
from fitness_bot.service.handlers.commands.session import (
    FinalizeSessionCommandHandler,
    GenerateNextSessionCommandHandler,
    StartTodayWorkoutCommandHandler,
)
from fitness_bot.service.handlers.commands.training_reminder import (
    MarkTrainingReminderSentCommandHandler,
    SkipTrainingDayCommandHandler,
    ToggleTrainingReminderCommandHandler,
)
from fitness_bot.service.handlers.commands.users import EnsureUserCommandHandler
from fitness_bot.service.handlers.queries.training_reminder import (
    GetTrainingReminderSettingsQueryHandler,
    ListDueTrainingRemindersQueryHandler,
)
from fitness_bot.service.models.commands.body import RecordWellbeingCommand
from fitness_bot.service.models.commands.session import (
    FinalizeSessionCommand,
    GenerateNextSessionCommand,
    StartTodayWorkoutCommand,
)
from fitness_bot.service.models.commands.training_reminder import (
    MarkTrainingReminderSentCommand,
    SkipTrainingDayCommand,
    ToggleTrainingReminderCommand,
)
from fitness_bot.service.models.commands.users import EnsureUserCommand
from fitness_bot.service.models.queries.training_reminder import (
    GetTrainingReminderSettingsQuery,
    ListDueTrainingRemindersQuery,
)
from fitness_bot.service.ports.exercise_catalog import InMemoryExerciseCatalog, record

TG = 77
# 2026-10-19 is Monday. +03:00 makes 17:00 UTC = 20:00 local, 06:00 UTC = 09:00 local.
MONDAY_EVENING = datetime(2026, 10, 19, 17, 0, tzinfo=UTC)
MONDAY_MORNING = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
MONDAY_LATE = datetime(2026, 10, 19, 18, 0, tzinfo=UTC)
EXERCISE_ID = uuid4()


def _day(weekday: int, title: str) -> WorkoutDay:
    return WorkoutDay(
        weekday=weekday,
        title=title,
        position=weekday,
        slots=[ExerciseSlot(position=1, exercise_id=EXERCISE_ID, sets=3, reps=8, rest_seconds=90, rpe=7)],
    )


async def _seed(uow: InMemoryUow, weekdays: list[tuple[int, str]] | None, *, timezone_offset: str | None = "+03:00"):
    await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=TG, chat_id=770))
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None
        user.timezone_offset = timezone_offset
        user.goal = Goal.MUSCLE_GAIN
        if weekdays is not None:
            program = Program(
                user_id=user.id,
                program_type=ProgramType.FULL_BODY,
                status=ProgramStatus.ACTIVE,
                days=[_day(weekday, title) for weekday, title in weekdays],
                activated_at=datetime.now(UTC) - timedelta(days=2),
            )
            await repos.programs.add(program)
            user.active_program_id = program.id
        await repos.users.save(user)
        return user


async def _due(uow: InMemoryUow, now: datetime):
    return await ListDueTrainingRemindersQueryHandler(uow).handle(ListDueTrainingRemindersQuery(now=now))


async def test_new_user_has_both_training_reminders_on() -> None:
    uow = InMemoryUow()
    await _seed(uow, None)
    settings = await GetTrainingReminderSettingsQueryHandler(uow).handle(
        GetTrainingReminderSettingsQuery(telegram_user_id=TG),
    )
    assert settings.evening_enabled is True
    assert settings.morning_enabled is True


async def test_evening_reminder_is_about_tomorrows_workout() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(1, "Верх"), (2, "Ноги")])
    due = await _due(uow, MONDAY_EVENING)
    assert len(due.items) == 1
    item = due.items[0]
    assert item.kind == "evening"
    assert item.day_title == "Ноги"
    assert item.target_date == date(2026, 10, 20)
    assert item.sent_on == date(2026, 10, 19)


async def test_morning_reminder_is_about_today_and_survives_a_late_tick() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(1, "Верх"), (2, "Ноги")])
    early = await _due(uow, datetime(2026, 10, 19, 5, 59, tzinfo=UTC))
    assert early.items == []
    due = await _due(uow, datetime(2026, 10, 19, 6, 15, tzinfo=UTC))
    assert [item.kind for item in due.items] == ["morning"]
    assert due.items[0].day_title == "Верх"
    assert due.items[0].target_date == date(2026, 10, 19)


async def test_late_evening_does_not_also_send_the_morning_nudge() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(1, "Верх"), (2, "Ноги")])
    due = await _due(uow, MONDAY_LATE)
    assert [item.kind for item in due.items] == ["evening"]


async def test_rest_day_completed_day_and_repeat_are_skipped() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(1, "Верх")])
    assert (await _due(uow, MONDAY_EVENING)).items == []

    uow = InMemoryUow()
    await _seed(uow, [(1, "Верх"), (2, "Ноги")])
    await StartTodayWorkoutCommandHandler(uow).handle(StartTodayWorkoutCommand(telegram_user_id=TG, weekday=2))
    await FinalizeSessionCommandHandler(uow).handle(FinalizeSessionCommand(telegram_user_id=TG))
    assert (await _due(uow, MONDAY_EVENING)).items == []

    uow = InMemoryUow()
    await _seed(uow, [(1, "Верх"), (2, "Ноги")])
    user_id = (await _due(uow, MONDAY_EVENING)).items[0].user_id
    await MarkTrainingReminderSentCommandHandler(uow).handle(
        MarkTrainingReminderSentCommand(user_id=user_id, kind="evening", sent_on=date(2026, 10, 19)),
    )
    assert (await _due(uow, MONDAY_EVENING)).items == []


async def test_morning_skips_an_open_session_and_a_finished_today() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(1, "Верх")])
    await StartTodayWorkoutCommandHandler(uow).handle(StartTodayWorkoutCommand(telegram_user_id=TG, weekday=1))
    assert (await _due(uow, MONDAY_MORNING)).items == []

    await FinalizeSessionCommandHandler(uow).handle(FinalizeSessionCommand(telegram_user_id=TG))
    assert (await _due(uow, MONDAY_MORNING)).items == []


async def test_training_reminder_ignores_expected_input_and_missing_timezone() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(1, "Верх")], timezone_offset=None)
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None
        user.expected_input = ExpectedInput.WEIGHT
        await repos.users.save(user)
    due = await _due(uow, datetime(2026, 10, 19, 9, 0, tzinfo=UTC))
    assert [item.kind for item in due.items] == ["morning"]


async def test_toggle_turns_a_nudge_off() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(1, "Верх"), (2, "Ноги")])
    await ToggleTrainingReminderCommandHandler(uow).handle(
        ToggleTrainingReminderCommand(telegram_user_id=TG, kind="evening"),
    )
    assert (await _due(uow, MONDAY_EVENING)).items == []
    morning = await _due(uow, MONDAY_MORNING)
    assert [item.kind for item in morning.items] == ["morning"]


async def test_skip_cascades_the_week_and_reports_the_moves() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(1, "Верх"), (2, "Ноги")])
    result = await SkipTrainingDayCommandHandler(uow).handle(
        SkipTrainingDayCommand(telegram_user_id=TG, local_date=date(2026, 10, 19)),
    )
    assert result.outcome == "shifted"
    assert [(move.title, move.from_weekday, move.to_weekday) for move in result.moves] == [
        ("Верх", 1, 2),
        ("Ноги", 2, 3),
    ]
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None and user.active_program_id is not None
        program = await repos.programs.get_by_id(user.active_program_id)
    assert program is not None
    assert sorted(day.weekday for day in program.days) == [2, 3]


async def test_skip_of_a_full_week_leaves_the_plan() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(weekday, f"День {weekday}") for weekday in range(1, 8)])
    result = await SkipTrainingDayCommandHandler(uow).handle(
        SkipTrainingDayCommand(telegram_user_id=TG, local_date=date(2026, 10, 19)),
    )
    assert result.outcome == "cannot_shift"
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None and user.active_program_id is not None
        program = await repos.programs.get_by_id(user.active_program_id)
    assert program is not None
    assert sorted(day.weekday for day in program.days if day.weekday) == list(range(1, 8))


class _CapturingModel:
    def __init__(self, response: str, *, fail: Exception | None = None) -> None:
        self.response = response
        self.fail = fail
        self.user = ""

    async def complete(self, *, system: str, user: str) -> str:
        _ = system
        self.user = user
        if self.fail is not None:
            raise self.fail
        return self.response


def _draft_json() -> str:
    return json.dumps(
        {
            "document": {
                "program_type": "full_body",
                "days": [
                    {
                        "weekday": 2,
                        "title": "Завтрашняя+",
                        "position": 2,
                        "slots": [
                            {
                                "position": 1,
                                "exercise_id": str(EXERCISE_ID),
                                "sets": 3,
                                "reps": 8,
                                "duration_seconds": None,
                                "weight_kg": None,
                                "rest_seconds": 90,
                                "rpe": 7,
                                "technique_note": "",
                            },
                        ],
                    },
                ],
            },
            "reply": "Черновик.",
        },
    )


async def test_evening_yes_prepares_tomorrows_draft_without_starting() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(1, "Сегодняшняя"), (2, "Завтрашняя")])
    await RecordWellbeingCommandHandler(uow).handle(
        RecordWellbeingCommand(telegram_user_id=TG, text="болело колено"),
    )
    model = _CapturingModel(_draft_json())
    result = await GenerateNextSessionCommandHandler(
        uow,
        model,
        InMemoryExerciseCatalog(
            exercises=[record(exercise_id=EXERCISE_ID, name="Жим", primary_muscles=["грудь"])],
        ),
    ).handle(GenerateNextSessionCommand(telegram_user_id=TG, target_weekday=2))
    assert result.proposal_id is not None
    assert result.document is not None
    assert "Завтрашняя" in model.user
    assert "болело колено" in model.user
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None
        assert user.active_session_id is None
        assert user.pending_proposal_id == result.proposal_id
        program = await repos.programs.get_by_id(user.active_program_id)  # type: ignore[arg-type]
    assert program is not None
    assert {day.weekday for day in program.days} == {1, 2}


async def test_failed_prepare_keeps_the_program() -> None:
    uow = InMemoryUow()
    await _seed(uow, [(1, "Сегодняшняя"), (2, "Завтрашняя")])
    catalog = InMemoryExerciseCatalog(
        exercises=[record(exercise_id=EXERCISE_ID, name="Жим", primary_muscles=["грудь"])],
    )
    result = await GenerateNextSessionCommandHandler(
        uow,
        _CapturingModel("", fail=AgentUnavailable("down")),
        catalog,
    ).handle(GenerateNextSessionCommand(telegram_user_id=TG, target_weekday=2))
    assert result.agent_unavailable is True
    assert result.proposal_id is None
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(TG)
        assert user is not None and user.active_session_id is None and user.pending_proposal_id is None
        program = await repos.programs.get_by_id(user.active_program_id)  # type: ignore[arg-type]
    assert program is not None
    assert {day.weekday for day in program.days} == {1, 2}
