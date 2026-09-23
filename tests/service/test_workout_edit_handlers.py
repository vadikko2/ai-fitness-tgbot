from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fitness_bot.domain.enums import Goal, ProfileField, ProgramType, Sex, WeightSource
from fitness_bot.domain.errors import AgentUnavailable
from fitness_bot.domain.users.user import local_calendar_date
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay, WorkoutDocument
from fitness_bot.infrastructure.adapters.object_storage import InMemoryObjectStorage
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.body import RecordWeightCommandHandler
from fitness_bot.service.handlers.commands.program import (
    ApproveProposalCommandHandler,
    DiscardProposalCommandHandler,
    ProposeProgramChangeCommandHandler,
    ProposeProgramCommandHandler,
    SelectExerciseForProposalCommandHandler,
)
from fitness_bot.service.handlers.commands.session import (
    ProposeWorkoutChangeCommandHandler,
    StartSessionFromTemplateCommandHandler,
)
from fitness_bot.service.handlers.commands.users import (
    EnsureUserCommandHandler,
    SetGoalCommandHandler,
    UpdateProfileCommandHandler,
)
from fitness_bot.service.handlers.queries.program import GetPendingProposalQueryHandler
from fitness_bot.service.handlers.queries.session import GetTodayWorkoutQueryHandler
from fitness_bot.service.models.commands.body import RecordWeightCommand
from fitness_bot.service.models.commands.program import (
    ApproveProposalCommand,
    DiscardProposalCommand,
    ProposeProgramChangeCommand,
    ProposeProgramCommand,
    SelectExerciseForProposalCommand,
)
from fitness_bot.service.models.commands.session import ProposeWorkoutChangeCommand, StartSessionFromTemplateCommand
from fitness_bot.service.models.commands.users import EnsureUserCommand, SetGoalCommand, UpdateProfileCommand
from fitness_bot.service.models.queries.program import GetPendingProposalQuery
from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery
from fitness_bot.service.ports.exercise_catalog import InMemoryExerciseCatalog, record
from tests.support.program_flow import choose_program_structure_and_style

EX_A = uuid4()
EX_B = uuid4()


class ScriptedLanguageModel:
    def __init__(self, responses: list[str] | None = None, *, fail: Exception | None = None) -> None:
        self._responses = list(responses or [])
        self._fail = fail
        self.calls = 0

    async def complete(self, *, system: str, user: str) -> str:
        _ = system, user
        self.calls += 1
        if self._fail is not None:
            raise self._fail
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
    import json

    weekday = _today_weekday()
    other = 1 if weekday != 1 else 2
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
                            "custom_request": None,
                            "muscle_group": None,
                            "sets": 3,
                            "reps": 8,
                            "duration_seconds": None,
                            "weight_kg": 60,
                            "rest_seconds": 90,
                            "rpe": 7,
                            "technique_note": "",
                        },
                    ],
                },
                {
                    "weekday": other,
                    "title": "Другой день",
                    "position": 2,
                    "slots": [
                        {
                            "position": 1,
                            "exercise_id": str(EX_B),
                            "custom_request": None,
                            "muscle_group": None,
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
                    "weekday": ((weekday % 7) + 1) if (weekday % 7) + 1 != other else ((weekday + 2 - 1) % 7) + 1,
                    "title": "Третий",
                    "position": 3,
                    "slots": [
                        {
                            "position": 1,
                            "exercise_id": str(EX_B),
                            "custom_request": None,
                            "muscle_group": None,
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
    # Ensure three distinct weekdays matching days_per_week=3.
    days = payload["program"]["days"]
    used = {days[0]["weekday"], days[1]["weekday"]}
    third = next(d for d in range(1, 8) if d not in used)
    days[2]["weekday"] = third
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


async def _activate_program_with_today(uow: InMemoryUow) -> None:
    lm = ScriptedLanguageModel([_week_json_for_today()])
    await choose_program_structure_and_style(uow, program_type=ProgramType.FULL_BODY)
    await ProposeProgramCommandHandler(uow, lm, _catalog()).handle(ProposeProgramCommand(telegram_user_id=7))
    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.program_id is not None


def _session_edit_json(*, unresolved: bool = False, sets: int = 4) -> str:
    import json

    weekday = _today_weekday()
    slot = {
        "position": 1,
        "exercise_id": None if unresolved else str(EX_B),
        "custom_request": "тяга" if unresolved else None,
        "muscle_group": "спина" if unresolved else None,
        "sets": sets,
        "reps": 10,
        "duration_seconds": None,
        "weight_kg": 55,
        "rest_seconds": 90,
        "rpe": 8,
        "technique_note": "",
    }
    payload = {
        "document": {
            "program_type": "full_body",
            "days": [{"weekday": weekday, "title": "Сегодня", "position": 1, "slots": [slot]}],
        },
        "reply": "Обновил тренировку.",
    }
    return json.dumps(payload, ensure_ascii=False)


async def test_start_session_then_edit_approve(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program_with_today(uow)
    started = await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )
    assert started.document.days[0].slots[0].exercise_id == EX_A

    lm = ScriptedLanguageModel([_session_edit_json(unresolved=False, sets=5)])
    first = await ProposeWorkoutChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeWorkoutChangeCommand(telegram_user_id=7, utterance="Сделай 5 подходов"),
    )
    assert first.proposal_id is not None
    assert first.document is not None
    assert first.document.days[0].slots[0].sets == 5

    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.session_id == started.session_id
    assert approved.document is not None
    assert approved.document.days[0].slots[0].sets == 5

    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen == "session"
    assert today.document is not None
    assert today.document.days[0].slots[0].sets == 5


async def test_second_utterance_keeps_same_proposal(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program_with_today(uow)
    await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )
    lm = ScriptedLanguageModel(
        [
            _session_edit_json(sets=4),
            _session_edit_json(sets=6),
        ],
    )
    first = await ProposeWorkoutChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeWorkoutChangeCommand(telegram_user_id=7, utterance="4 подхода"),
    )
    second = await ProposeWorkoutChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeWorkoutChangeCommand(telegram_user_id=7, utterance="6 подходов"),
    )
    assert first.proposal_id == second.proposal_id
    assert second.document is not None
    assert second.document.days[0].slots[0].sets == 6
    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.proposal_id == first.proposal_id


async def test_approve_unresolved_workout_edit_blocked(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program_with_today(uow)
    await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )
    lm = ScriptedLanguageModel([_session_edit_json(unresolved=True)])
    await ProposeWorkoutChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeWorkoutChangeCommand(telegram_user_id=7, utterance="добавь тягу"),
    )
    result = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert result.blocked_unresolved is True
    assert result.session_id is None
    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.document is not None
    assert today.document.days[0].slots[0].exercise_id == EX_A


async def test_select_exercise_then_approve_workout_edit(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program_with_today(uow)
    await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )
    lm = ScriptedLanguageModel([_session_edit_json(unresolved=True)])
    proposed = await ProposeWorkoutChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeWorkoutChangeCommand(telegram_user_id=7, utterance="тяга"),
    )
    assert proposed.document is not None
    day_position = proposed.document.days[0].position
    selected = await SelectExerciseForProposalCommandHandler(uow, _catalog()).handle(
        SelectExerciseForProposalCommand(
            telegram_user_id=7,
            day_position=day_position,
            slot_position=1,
            exercise_id=EX_B,
        ),
    )
    assert selected.document.unresolved_slots() == []
    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.session_id is not None
    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.document is not None
    assert today.document.days[0].slots[0].exercise_id == EX_B


async def test_agent_unavailable_does_not_mutate_session(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program_with_today(uow)
    started = await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )
    lm = ScriptedLanguageModel(fail=TimeoutError("timeout"))
    result = await ProposeWorkoutChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeWorkoutChangeCommand(telegram_user_id=7, utterance="поменяй"),
    )
    assert result.agent_unavailable is True
    assert result.document is None
    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.proposal_id is None
    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.document is not None
    assert today.document.days[0].slots[0].exercise_id == started.document.days[0].slots[0].exercise_id


async def test_discard_workout_edit_keeps_session(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program_with_today(uow)
    await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )
    lm = ScriptedLanguageModel([_session_edit_json(sets=9)])
    await ProposeWorkoutChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeWorkoutChangeCommand(telegram_user_id=7, utterance="9"),
    )
    await DiscardProposalCommandHandler(uow).handle(DiscardProposalCommand(telegram_user_id=7))
    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen == "session"
    assert today.document is not None
    assert today.document.days[0].slots[0].sets == 3


async def test_program_change_second_utterance_same_draft(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await choose_program_structure_and_style(uow, program_type=ProgramType.FULL_BODY)
    doc = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="День 1",
                position=1,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=EX_A,
                        sets=3,
                        reps=8,
                        rest_seconds=90,
                        rpe=7,
                    ),
                ],
            ),
            WorkoutDay(
                weekday=3,
                title="День 2",
                position=2,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=EX_B,
                        sets=3,
                        reps=10,
                        rest_seconds=90,
                        rpe=7,
                    ),
                ],
            ),
            WorkoutDay(
                weekday=5,
                title="День 3",
                position=3,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=EX_B,
                        sets=3,
                        reps=10,
                        rest_seconds=90,
                        rpe=7,
                    ),
                ],
            ),
        ],
    )
    import json

    first_payload = json.dumps({"document": doc.model_dump(mode="json"), "reply": "ок"}, ensure_ascii=False)
    doc2 = doc.model_copy(deep=True)
    doc2.days[0].slots[0] = doc2.days[0].slots[0].model_copy(update={"sets": 5})
    second_payload = json.dumps({"document": doc2.model_dump(mode="json"), "reply": "ещё"}, ensure_ascii=False)
    lm = ScriptedLanguageModel([first_payload, second_payload])
    first = await ProposeProgramChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeProgramChangeCommand(telegram_user_id=7, utterance="собери"),
    )
    second = await ProposeProgramChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeProgramChangeCommand(telegram_user_id=7, utterance="5 подходов"),
    )
    assert first.proposal_id == second.proposal_id
    assert second.document is not None
    assert second.document.days[0].slots[0].sets == 5


async def test_program_change_day_scope_keeps_other_days(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await choose_program_structure_and_style(uow, program_type=ProgramType.FULL_BODY)
    import json

    base = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="День 1",
                position=1,
                warmup="старая разминка",
                cooldown="старая заминка",
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=EX_A,
                        sets=3,
                        reps=8,
                        rest_seconds=90,
                        rpe=7,
                    ),
                ],
            ),
            WorkoutDay(
                weekday=3,
                title="День 2",
                position=2,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=EX_B,
                        sets=3,
                        reps=10,
                        rest_seconds=90,
                        rpe=7,
                    ),
                ],
            ),
            WorkoutDay(
                weekday=5,
                title="День 3",
                position=3,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=EX_B,
                        sets=4,
                        reps=12,
                        rest_seconds=90,
                        rpe=7,
                    ),
                ],
            ),
        ],
    )
    seed = json.dumps({"document": base.model_dump(mode="json"), "reply": "база"}, ensure_ascii=False)
    await ProposeProgramChangeCommandHandler(uow, ScriptedLanguageModel([seed]), _catalog()).handle(
        ProposeProgramChangeCommand(telegram_user_id=7, utterance="собери"),
    )

    edited_day = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=1,
                title="День 1 — проще",
                position=1,
                warmup="5 мин кардио и мобилизация",
                cooldown="растяжка 3 мин",
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=EX_A,
                        sets=3,
                        reps=12,
                        rest_seconds=90,
                        rpe=6,
                    ),
                ],
            ),
        ],
    )
    day_payload = json.dumps(
        {"document": edited_day.model_dump(mode="json"), "reply": "упростил день 1"},
        ensure_ascii=False,
    )
    result = await ProposeProgramChangeCommandHandler(
        uow,
        ScriptedLanguageModel([day_payload]),
        _catalog(),
    ).handle(
        ProposeProgramChangeCommand(
            telegram_user_id=7,
            utterance="упрости упражнения",
            day_position=1,
        ),
    )
    assert result.document is not None
    assert result.day_position == 1
    assert len(result.document.days) == 3
    assert result.document.days[0].title == "День 1 — проще"
    assert result.document.days[0].warmup == "5 мин кардио и мобилизация"
    assert result.document.days[0].cooldown == "растяжка 3 мин"
    assert result.document.days[0].slots[0].reps == 12
    assert result.document.days[1].title == "День 2"
    assert result.document.days[1].slots[0].exercise_id == EX_B
    assert result.document.days[2].slots[0].sets == 4


async def test_agent_unavailable_error_type() -> None:
    assert issubclass(AgentUnavailable, Exception)
