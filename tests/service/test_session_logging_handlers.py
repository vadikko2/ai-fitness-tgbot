from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from fitness_bot.domain.enums import (
    ExpectedInput,
    Goal,
    ProfileField,
    ProgramType,
    SessionStatus,
    Sex,
    WeightSource,
)
from fitness_bot.domain.users.user import local_calendar_date
from fitness_bot.infrastructure.adapters.object_storage import InMemoryObjectStorage
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.body import RecordWeightCommandHandler
from fitness_bot.service.handlers.commands.program import (
    ApproveProposalCommandHandler,
    ProposeProgramCommandHandler,
)
from fitness_bot.service.handlers.commands.session import (
    BeginSessionCompletionCommandHandler,
    ConfirmExerciseAsPlannedCommandHandler,
    FinalizeSessionCommandHandler,
    ProposeSessionDeviationCommandHandler,
    ProposeSlotActualCommandHandler,
    RestartOpenSessionCommandHandler,
    StartSessionFromTemplateCommandHandler,
)
from fitness_bot.service.handlers.commands.users import (
    EnsureUserCommandHandler,
    ExpectInputCommandHandler,
    SetGoalCommandHandler,
    UpdateProfileCommandHandler,
)
from fitness_bot.service.handlers.queries.session import GetTodayWorkoutQueryHandler
from fitness_bot.service.models.commands.body import RecordWeightCommand
from fitness_bot.service.models.commands.program import (
    ApproveProposalCommand,
    ProposeProgramCommand,
)
from fitness_bot.service.models.commands.session import (
    BeginSessionCompletionCommand,
    ConfirmExerciseAsPlannedCommand,
    FinalizeSessionCommand,
    ProposeSessionDeviationCommand,
    ProposeSlotActualCommand,
    RestartOpenSessionCommand,
    StartSessionFromTemplateCommand,
)
from fitness_bot.service.models.commands.users import (
    EnsureUserCommand,
    ExpectInputCommand,
    SetGoalCommand,
    UpdateProfileCommand,
)
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery
from fitness_bot.service.ports.exercise_catalog import InMemoryExerciseCatalog, record
from tests.support.program_flow import choose_program_structure_and_style

EX_A = uuid4()
EX_B = uuid4()


class ScriptedLanguageModel:
    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or [])
        self.calls = 0

    async def complete(self, *, system: str, user: str) -> str:
        _ = system, user
        self.calls += 1
        if not self._responses:
            raise AssertionError("no scripted responses left")
        return self._responses.pop(0)


def _catalog() -> InMemoryExerciseCatalog:
    return InMemoryExerciseCatalog(
        exercises=[
            record(exercise_id=EX_A, name="Жим лёжа", primary_muscles=["грудь"]),
            record(exercise_id=EX_B, name="Тяга штанги", primary_muscles=["спина"]),
        ],
    )


def _today_weekday() -> int:
    return local_calendar_date(now=datetime.now(UTC), timezone_offset="+03:00").isoweekday()


def _week_json_for_today() -> str:
    weekday = _today_weekday()
    other = 1 if weekday != 1 else 2
    used = {weekday, other}
    third = next(d for d in range(1, 8) if d not in used)
    payload = {
        "program": {
            "program_type": "full_body",
            "days": [
                {
                    "weekday": weekday,
                    "title": "Сегодня",
                    "position": 1,
                    "slots": [
                        {
                            "position": 1,
                            "exercise_id": str(EX_A),
                            "sets": 3,
                            "reps": 8,
                            "duration_seconds": None,
                            "weight_kg": 60,
                            "rest_seconds": 90,
                            "rpe": 7,
                            "technique_note": "",
                        },
                        {
                            "position": 2,
                            "exercise_id": str(EX_B),
                            "sets": 3,
                            "reps": 10,
                            "duration_seconds": None,
                            "weight_kg": 50,
                            "rest_seconds": 90,
                            "rpe": 7,
                            "technique_note": "",
                        },
                    ],
                },
                {
                    "weekday": other,
                    "title": "Другой",
                    "position": 2,
                    "slots": [
                        {
                            "position": 1,
                            "exercise_id": str(EX_B),
                            "sets": 3,
                            "reps": 10,
                            "duration_seconds": None,
                            "weight_kg": 50,
                            "rest_seconds": 90,
                            "rpe": 7,
                            "technique_note": "",
                        },
                    ],
                },
                {
                    "weekday": third,
                    "title": "Третий",
                    "position": 3,
                    "slots": [
                        {
                            "position": 1,
                            "exercise_id": str(EX_B),
                            "sets": 3,
                            "reps": 10,
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
        "reply": "Неделя готова.",
    }
    return json.dumps(payload, ensure_ascii=False)


@pytest.fixture
def uow() -> InMemoryUow:
    return InMemoryUow()


async def _seed_profile(uow: InMemoryUow, telegram_user_id: int = 7) -> None:
    await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=telegram_user_id, chat_id=70))
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.SEX, value=Sex.MALE.value),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.BIRTH_YEAR, value=1995),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.HEIGHT, value="180"),
    )
    await RecordWeightCommandHandler(uow).handle(
        RecordWeightCommand(telegram_user_id=telegram_user_id, kilograms="80", source=WeightSource.ONBOARDING),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.EXPERIENCE, value="beginner"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.DAYS_PER_WEEK, value=3),
    )
    weekday = _today_weekday()
    others = [d for d in range(1, 8) if d != weekday][:2]
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(
            telegram_user_id=telegram_user_id,
            field=ProfileField.TRAINING_WEEKDAYS,
            value=[weekday, *others],
        ),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.EQUIPMENT, value="зал"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.LIMITATIONS, value=""),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.ACTIVITY_LEVEL, value="moderate"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.SESSION_MINUTES, value=60),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.BODY_FAT, value="unknown"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.SUPPLEMENTS, value=["none"]),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.DIET_PREFS, value=""),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.TIMEZONE, value="+03:00"),
    )
    await SetGoalCommandHandler(uow).handle(SetGoalCommand(telegram_user_id=telegram_user_id, goal=Goal.MUSCLE_GAIN))


async def _start_session(uow: InMemoryUow):
    await _seed_profile(uow)
    lm = ScriptedLanguageModel([_week_json_for_today()])
    await choose_program_structure_and_style(uow, program_type=ProgramType.FULL_BODY)
    await ProposeProgramCommandHandler(uow, lm, _catalog()).handle(ProposeProgramCommand(telegram_user_id=7))
    await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    return await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )


def _performance_json(*, sets: int = 4, reps: int = 6, weight: str = "55") -> str:
    return json.dumps(
        {
            "slot": {
                "position": 1,
                "exercise_id": str(EX_A),
                "sets": 3,
                "reps": 8,
                "duration_seconds": None,
                "weight_kg": 60,
                "rest_seconds": 90,
                "rpe": 7,
                "technique_note": "",
                "actual": {
                    "sets": sets,
                    "reps": reps,
                    "duration_seconds": None,
                    "weight_kg": weight,
                    "note": "чуть легче",
                },
            },
            "reply": "Записал факт.",
        },
        ensure_ascii=False,
    )


def _deviation_json(*, sets: int = 2) -> str:
    return json.dumps(
        {
            "document": {
                "program_type": "full_body",
                "days": [
                    {
                        "weekday": _today_weekday(),
                        "title": "Сегодня",
                        "position": 1,
                        "slots": [
                            {
                                "position": 1,
                                "exercise_id": str(EX_A),
                                "sets": 3,
                                "reps": 8,
                                "duration_seconds": None,
                                "weight_kg": 60,
                                "rest_seconds": 90,
                                "rpe": 7,
                                "technique_note": "",
                                "actual": {
                                    "sets": sets,
                                    "reps": 8,
                                    "duration_seconds": None,
                                    "weight_kg": 60,
                                    "note": "сократил",
                                },
                            },
                            {
                                "position": 2,
                                "exercise_id": str(EX_B),
                                "sets": 3,
                                "reps": 10,
                                "duration_seconds": None,
                                "weight_kg": 50,
                                "rest_seconds": 90,
                                "rpe": 7,
                                "technique_note": "",
                                "actual": {
                                    "sets": 3,
                                    "reps": 10,
                                    "duration_seconds": None,
                                    "weight_kg": 50,
                                    "note": "",
                                },
                            },
                        ],
                    },
                ],
            },
            "reply": "Поправил факт.",
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_confirm_exercise_as_planned(uow: InMemoryUow) -> None:
    started = await _start_session(uow)
    result = await ConfirmExerciseAsPlannedCommandHandler(uow).handle(
        ConfirmExerciseAsPlannedCommand(telegram_user_id=7, slot_position=1),
    )
    assert result.session_id == started.session_id
    assert result.slot.actual is not None
    assert result.slot.actual.sets == 3
    assert result.slot.actual.reps == 8
    assert result.slot.actual.weight_kg == Decimal("60")
    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen == "session"
    assert today.document is not None
    assert today.document.days[0].slots[0].actual is not None
    assert today.document.days[0].slots[1].actual is None


@pytest.mark.asyncio
async def test_propose_slot_actual_then_approve(uow: InMemoryUow) -> None:
    await _start_session(uow)
    await ExpectInputCommandHandler(uow).handle(
        ExpectInputCommand(
            telegram_user_id=7,
            expected_input=ExpectedInput.PROPOSAL_UTTERANCE,
            expected_field="slot_actual",
            focus_slot=1,
        ),
    )
    lm = ScriptedLanguageModel([_performance_json(sets=4, reps=6, weight="55")])
    proposed = await ProposeSlotActualCommandHandler(uow, lm).handle(
        ProposeSlotActualCommand(telegram_user_id=7, utterance="4 на 6 с 55"),
    )
    assert proposed.proposal_id is not None
    assert proposed.document is not None
    assert proposed.document.days[0].slots[0].actual is not None
    assert proposed.document.days[0].slots[0].actual.sets == 4

    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.session_id is not None
    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.document is not None
    actual = today.document.days[0].slots[0].actual
    assert actual is not None
    assert actual.sets == 4
    assert actual.reps == 6
    assert actual.weight_kg == Decimal("55")
    assert actual.note == "чуть легче"
    # Planned fields unchanged.
    assert today.document.days[0].slots[0].sets == 3
    assert today.document.days[0].slots[0].reps == 8


@pytest.mark.asyncio
async def test_complete_entire_workout_as_planned(uow: InMemoryUow) -> None:
    started = await _start_session(uow)
    begun = await BeginSessionCompletionCommandHandler(uow).handle(
        BeginSessionCompletionCommand(telegram_user_id=7),
    )
    assert begun.session_status == SessionStatus.PENDING_COMPLETION
    assert all(slot.actual is not None for slot in begun.document.days[0].slots)
    assert begun.document.days[0].slots[0].actual is not None
    assert begun.document.days[0].slots[0].actual.sets == 3

    finalized = await FinalizeSessionCommandHandler(uow).handle(FinalizeSessionCommand(telegram_user_id=7))
    assert finalized.session_id == started.session_id
    assert finalized.session_status == SessionStatus.COMPLETED
    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen == "template"
    assert today.session_id is None


@pytest.mark.asyncio
async def test_complete_with_deviation_then_finalize(uow: InMemoryUow) -> None:
    await _start_session(uow)
    await BeginSessionCompletionCommandHandler(uow).handle(BeginSessionCompletionCommand(telegram_user_id=7))
    lm = ScriptedLanguageModel([_deviation_json(sets=2)])
    proposed = await ProposeSessionDeviationCommandHandler(uow, lm, _catalog()).handle(
        ProposeSessionDeviationCommand(telegram_user_id=7, utterance="на жиме сделал только 2 подхода"),
    )
    assert proposed.proposal_id is not None
    assert proposed.document is not None
    assert proposed.document.days[0].slots[0].actual is not None
    assert proposed.document.days[0].slots[0].actual.sets == 2

    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.session_id is not None
    finalized = await FinalizeSessionCommandHandler(uow).handle(FinalizeSessionCommand(telegram_user_id=7))
    assert finalized.session_status == SessionStatus.COMPLETED
    assert finalized.document.days[0].slots[0].actual is not None
    assert finalized.document.days[0].slots[0].actual.sets == 2
    # Template day on the program must stay as planned (no actuals).
    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen == "template"
    assert today.document is not None
    assert today.document.days[0].slots[0].actual is None
    assert today.document.days[0].slots[0].sets == 3


@pytest.mark.asyncio
async def test_start_after_completed_asks_confirm_then_overwrite(uow: InMemoryUow) -> None:
    started = await _start_session(uow)
    old_session_id = started.session_id
    await ConfirmExerciseAsPlannedCommandHandler(uow).handle(
        ConfirmExerciseAsPlannedCommand(telegram_user_id=7, slot_position=1),
    )
    await BeginSessionCompletionCommandHandler(uow).handle(BeginSessionCompletionCommand(telegram_user_id=7))
    finalized = await FinalizeSessionCommandHandler(uow).handle(FinalizeSessionCommand(telegram_user_id=7))
    assert finalized.session_status == SessionStatus.COMPLETED
    assert finalized.document.days[0].slots[0].actual is not None

    blocked = await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )
    assert blocked.needs_repeat_confirmation is True
    assert blocked.session_id is None
    assert blocked.document is None

    repeated = await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7, overwrite_completed=True),
    )
    assert repeated.needs_repeat_confirmation is False
    assert repeated.session_id is not None
    assert repeated.session_id != old_session_id
    assert repeated.document is not None
    assert all(slot.actual is None for slot in repeated.document.days[0].slots)

    async with uow.transaction() as repos:
        old = await repos.sessions.get_by_id(old_session_id)
        assert old is None
        user = await repos.users.get_by_telegram_id(7)
        assert user is not None
        history = await repos.sessions.list_completed_for_user(user.id, limit=10)
        assert history == []
        open_session = await repos.sessions.get_open_for_user(user.id)
        assert open_session is not None
        assert open_session.id == repeated.session_id


@pytest.mark.asyncio
async def test_restart_open_session_clears_actuals_and_technique_videos(uow: InMemoryUow) -> None:
    from fitness_bot.service.handlers.commands.session import SaveTechniqueVideoCommandHandler
    from fitness_bot.service.models.commands.session import SaveTechniqueVideoCommand

    started = await _start_session(uow)
    storage = InMemoryObjectStorage()
    await ConfirmExerciseAsPlannedCommandHandler(uow).handle(
        ConfirmExerciseAsPlannedCommand(telegram_user_id=7, slot_position=1),
    )
    await ExpectInputCommandHandler(uow).handle(
        ExpectInputCommand(
            telegram_user_id=7,
            expected_input=ExpectedInput.TECHNIQUE_VIDEO,
            focus_slot=1,
        ),
    )
    saved_video = await SaveTechniqueVideoCommandHandler(uow, storage).handle(
        SaveTechniqueVideoCommand(
            telegram_user_id=7,
            body=b"technique-bytes",
            content_type="video/mp4",
        ),
    )
    assert await storage.get(saved_video.object_key) == b"technique-bytes"

    restarted = await RestartOpenSessionCommandHandler(uow, storage).handle(
        RestartOpenSessionCommand(telegram_user_id=7),
    )
    assert restarted.session_id == started.session_id
    assert restarted.session_status == SessionStatus.IN_PROGRESS
    assert all(slot.actual is None for slot in restarted.document.days[0].slots)

    async with uow.transaction() as repos:
        videos = await repos.technique_videos.list_for_session(started.session_id)
        assert videos == []
        user = await repos.users.get_by_telegram_id(7)
        assert user is not None
        assert user.expected_input is ExpectedInput.NONE
    with pytest.raises(KeyError):
        await storage.get(saved_video.object_key)
