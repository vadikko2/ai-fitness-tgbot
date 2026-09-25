from __future__ import annotations

from uuid import uuid4

import pytest

from fitness_bot.domain.enums import ExpectedInput, Goal, ProfileField, ProgramType, Sex, WeightSource
from fitness_bot.domain.errors import AgentUnavailable
from fitness_bot.domain.workout.document import ExerciseSlot, WorkoutDay, WorkoutDocument
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.body import RecordWeightCommandHandler
from fitness_bot.service.handlers.commands.program import (
    ApproveProposalCommandHandler,
    ChooseProgramTypeCommandHandler,
    DiscardProposalCommandHandler,
    ProposeProgramChangeCommandHandler,
    ProposeProgramCommandHandler,
    SelectExerciseForProposalCommandHandler,
)
from fitness_bot.service.handlers.commands.users import (
    EnsureUserCommandHandler,
    SetGoalCommandHandler,
    UpdateProfileCommandHandler,
)
from fitness_bot.service.handlers.queries.program import GetActiveProgramQueryHandler, GetPendingProposalQueryHandler
from fitness_bot.service.models.commands.body import RecordWeightCommand
from fitness_bot.service.models.commands.program import (
    ApproveProposalCommand,
    ChooseProgramTypeCommand,
    DiscardProposalCommand,
    ProposeProgramChangeCommand,
    ProposeProgramCommand,
    SelectExerciseForProposalCommand,
)
from fitness_bot.service.models.commands.users import EnsureUserCommand, SetGoalCommand, UpdateProfileCommand
from fitness_bot.service.models.queries.program import GetActiveProgramQuery, GetPendingProposalQuery
from fitness_bot.service.ports.exercise_catalog import InMemoryExerciseCatalog, record
from tests.support.program_flow import choose_program_structure

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


def _week_json(*, unresolved: bool = False) -> str:
    import json

    slot_a = {
        "position": 1,
        "exercise_id": None if unresolved else str(EX_A),
        "custom_request": "жим" if unresolved else None,
        "muscle_group": "грудь" if unresolved else None,
        "sets": 3,
        "reps": 8,
        "duration_seconds": None,
        "weight_kg": 60,
        "rest_seconds": 90,
        "rpe": 7,
        "technique_note": "",
    }
    slot_b = {
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
    }
    payload = {
        "program": {
            "program_type": "full_body",
            "days": [
                {"weekday": 1, "title": "День 1", "position": 1, "slots": [slot_a]},
                {"weekday": 3, "title": "День 2", "position": 2, "slots": [slot_b]},
                {"weekday": 5, "title": "День 3", "position": 3, "slots": [slot_b]},
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
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.TRAINING_WEEKDAYS, value=[1, 3, 5]),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.EQUIPMENT, value="зал"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.TRAINING_PLACE, value="gym"),
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
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.NUTRITION_CONSTRAINTS, value=""),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=telegram_user_id, field=ProfileField.TIMEZONE, value="+03:00"),
    )
    await SetGoalCommandHandler(uow).handle(SetGoalCommand(telegram_user_id=telegram_user_id, goal=Goal.MUSCLE_GAIN))


def _resolved_document() -> WorkoutDocument:
    return WorkoutDocument(
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
                        weight_kg=60,
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


async def test_choose_type_does_not_create_active_program(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    result = await ChooseProgramTypeCommandHandler(uow).handle(
        ChooseProgramTypeCommand(telegram_user_id=7, program_type=ProgramType.SPLIT),
    )
    assert result.program_type == ProgramType.SPLIT
    active = await GetActiveProgramQueryHandler(uow).handle(GetActiveProgramQuery(telegram_user_id=7))
    assert active.program_id is None
    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.proposal_id == result.proposal_id
    assert pending.has_document is False


async def test_choose_type_sets_proposal_utterance_expectation(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await ChooseProgramTypeCommandHandler(uow).handle(
        ChooseProgramTypeCommand(telegram_user_id=7, program_type=ProgramType.FULL_BODY),
    )
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(7)
    assert user is not None
    assert user.expected_input == ExpectedInput.PROPOSAL_UTTERANCE
    assert user.expected_field == "program_edit"


async def test_approve_empty_week_blocked(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await choose_program_structure(uow, program_type=ProgramType.FULL_BODY)
    result = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert result.blocked_empty is True
    assert result.program_id is None
    active = await GetActiveProgramQueryHandler(uow).handle(GetActiveProgramQuery(telegram_user_id=7))
    assert active.program_id is None


async def test_approve_unresolved_blocked(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    lm = ScriptedLanguageModel([_week_json(unresolved=True)])
    await choose_program_structure(uow, program_type=ProgramType.FULL_BODY)
    proposed = await ProposeProgramCommandHandler(uow, lm, _catalog()).handle(
        ProposeProgramCommand(telegram_user_id=7),
    )
    assert proposed.document is not None
    assert proposed.document.unresolved_slots()
    result = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert result.blocked_unresolved is True
    assert result.program_id is None


async def test_propose_then_approve_creates_active_program(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    lm = ScriptedLanguageModel([_week_json(unresolved=False)])
    await choose_program_structure(uow, program_type=ProgramType.FULL_BODY)
    proposed = await ProposeProgramCommandHandler(uow, lm, _catalog()).handle(
        ProposeProgramCommand(telegram_user_id=7),
    )
    assert proposed.proposal_id is not None
    active_before = await GetActiveProgramQueryHandler(uow).handle(GetActiveProgramQuery(telegram_user_id=7))
    assert active_before.program_id is None

    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.program_id is not None
    assert approved.nutrition_stale is True
    active = await GetActiveProgramQueryHandler(uow).handle(GetActiveProgramQuery(telegram_user_id=7))
    assert active.program_id == approved.program_id
    assert active.document is not None
    assert len(active.document.days) == 3
    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.proposal_id is None


async def test_agent_unavailable_does_not_mutate_document(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await choose_program_structure(uow, program_type=ProgramType.FULL_BODY)
    lm = ScriptedLanguageModel(fail=TimeoutError("timeout"))
    result = await ProposeProgramCommandHandler(uow, lm, _catalog()).handle(ProposeProgramCommand(telegram_user_id=7))
    assert result.agent_unavailable is True
    assert result.document is None
    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.has_document is False


async def test_propose_invalid_json_returns_schema_failed(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await choose_program_structure(uow, program_type=ProgramType.FULL_BODY)
    lm = ScriptedLanguageModel(["not-json-at-all", "still-broken"])
    result = await ProposeProgramCommandHandler(uow, lm, _catalog()).handle(ProposeProgramCommand(telegram_user_id=7))
    assert result.schema_failed is True
    assert result.document is None
    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.has_document is False


async def test_select_exercise_then_approve(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    lm = ScriptedLanguageModel([_week_json(unresolved=True)])
    await choose_program_structure(uow, program_type=ProgramType.FULL_BODY)
    await ProposeProgramCommandHandler(uow, lm, _catalog()).handle(ProposeProgramCommand(telegram_user_id=7))
    selected = await SelectExerciseForProposalCommandHandler(uow, _catalog()).handle(
        SelectExerciseForProposalCommand(
            telegram_user_id=7,
            day_position=1,
            slot_position=1,
            exercise_id=EX_A,
        ),
    )
    assert selected.document.unresolved_slots() == []
    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.program_id is not None


async def test_text_path_change_then_approve(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await choose_program_structure(uow, program_type=ProgramType.FULL_BODY)
    doc = _resolved_document()
    import json

    payload = json.dumps(
        {"document": doc.model_dump(mode="json"), "reply": "Собрал неделю."},
        ensure_ascii=False,
    )
    lm = ScriptedLanguageModel([payload])
    changed = await ProposeProgramChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeProgramChangeCommand(telegram_user_id=7, utterance="Сделай фуллбади на три дня"),
    )
    assert changed.document is not None
    active_before = await GetActiveProgramQueryHandler(uow).handle(GetActiveProgramQuery(telegram_user_id=7))
    assert active_before.program_id is None
    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.program_id is not None


async def test_discard_clears_pending(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await choose_program_structure(uow, program_type=ProgramType.SPLIT)
    discarded = await DiscardProposalCommandHandler(uow).handle(DiscardProposalCommand(telegram_user_id=7))
    assert discarded.proposal_id is not None
    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.proposal_id is None


async def test_domain_empty_week_assert() -> None:
    doc = WorkoutDocument(program_type=ProgramType.SPLIT, days=[])
    with pytest.raises(Exception):
        doc.assert_approvable()


async def test_agent_unavailable_error_type() -> None:
    assert issubclass(AgentUnavailable, Exception)


def _tue_thu_sat_document() -> WorkoutDocument:
    return WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                weekday=2,
                title="Вторник",
                position=1,
                slots=[
                    ExerciseSlot(
                        position=1,
                        exercise_id=EX_A,
                        sets=3,
                        reps=8,
                        rest_seconds=90,
                        rpe=7,
                        weight_kg=60,
                    ),
                ],
            ),
            WorkoutDay(
                weekday=4,
                title="Четверг",
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
                weekday=6,
                title="Суббота",
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


async def test_free_text_tue_thu_sat_approve_syncs_weekdays_and_today_template(
    uow: InMemoryUow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from fitness_bot.service.handlers.queries.session import GetTodayWorkoutQueryHandler
    from fitness_bot.service.models.queries.session import GetTodayWorkoutQuery

    await _seed_profile(uow)
    await choose_program_structure(uow, program_type=ProgramType.FULL_BODY)
    doc = _tue_thu_sat_document()
    import json

    payload = json.dumps(
        {"document": doc.model_dump(mode="json"), "reply": "Вт/чт/сб готово."},
        ensure_ascii=False,
    )
    lm = ScriptedLanguageModel([payload])
    changed = await ProposeProgramChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeProgramChangeCommand(telegram_user_id=7, utterance="тренировки во вт чт сб"),
    )
    assert changed.document is not None
    assert [day.weekday for day in changed.document.days] == [2, 4, 6]

    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.program_id is not None
    assert approved.blocked_schedule is False

    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(7)
    assert user is not None
    assert user.days_per_week == 3
    assert user.training_weekdays == frozenset({2, 4, 6})

    # Freeze "today" to Tuesday (ISO weekday 2).
    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: object | None = None) -> datetime:
            return datetime(2026, 9, 22, 12, 0, tzinfo=UTC)

    monkeypatch.setattr(
        "fitness_bot.service.handlers.queries.session.datetime",
        _FrozenDateTime,
    )
    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen == "template"
    assert today.weekday == 2
    assert today.document is not None
    assert today.document.days[0].weekday == 2


async def test_approve_blocked_when_weekday_missing(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await choose_program_structure(uow, program_type=ProgramType.FULL_BODY)
    incomplete = WorkoutDocument(
        program_type=ProgramType.FULL_BODY,
        days=[
            WorkoutDay(
                title="Без дня недели",
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
        ],
    )
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(7)
        assert user is not None
        pending = await repos.proposals.get_pending_for_user(user.id)
        assert pending is not None
        pending.replace_document(incomplete, reply="черновик без weekday")
        await repos.proposals.save(pending)

    result = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert result.blocked_schedule is True
    assert result.program_id is None
    active = await GetActiveProgramQueryHandler(uow).handle(GetActiveProgramQuery(telegram_user_id=7))
    assert active.program_id is None


async def test_change_without_weekday_returns_schema_failed(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await choose_program_structure(uow, program_type=ProgramType.FULL_BODY)
    import json

    bad_doc = {
        "program_type": "full_body",
        "days": [
            {
                "title": "День 1",
                "position": 1,
                "slots": [
                    {
                        "position": 1,
                        "exercise_id": str(EX_A),
                        "sets": 3,
                        "reps": 8,
                        "rest_seconds": 90,
                        "rpe": 7,
                    },
                ],
            },
        ],
    }
    lm = ScriptedLanguageModel(
        [json.dumps({"document": bad_doc, "reply": "ок"}, ensure_ascii=False)] * 2,
    )
    result = await ProposeProgramChangeCommandHandler(uow, lm, _catalog()).handle(
        ProposeProgramChangeCommand(telegram_user_id=7, utterance="собери программу"),
    )
    assert result.schema_failed is True
    assert result.document is None
    assert result.reply == "ок"
