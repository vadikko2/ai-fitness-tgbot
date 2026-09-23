from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from fitness_bot.domain.enums import Goal, ProfileField, ProgramType, ProposalKind, SessionStatus, Sex, WeightSource
from fitness_bot.domain.errors import AgentUnavailable
from fitness_bot.domain.users.user import local_calendar_date
from fitness_bot.infrastructure.adapters.object_storage import InMemoryObjectStorage
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.body import RecordWeightCommandHandler
from fitness_bot.service.handlers.commands.nutrition import GenerateNutritionCommandHandler
from fitness_bot.service.handlers.commands.program import (
    ApproveProposalCommandHandler,
    GenerateNextWeekCommandHandler,
    ProposeProgramCommandHandler,
)
from fitness_bot.service.handlers.commands.session import (
    FinalizeSessionCommandHandler,
    GenerateNextSessionCommandHandler,
    StartSessionFromTemplateCommandHandler,
)
from fitness_bot.service.handlers.commands.users import (
    EnsureUserCommandHandler,
    SetGoalCommandHandler,
    UpdateProfileCommandHandler,
)
from fitness_bot.service.handlers.queries.nutrition import GetNutritionQueryHandler
from fitness_bot.service.handlers.queries.program import GetPendingProposalQueryHandler
from fitness_bot.service.handlers.queries.session import GetTodayWorkoutQueryHandler
from fitness_bot.service.models.commands.body import RecordWeightCommand
from fitness_bot.service.models.commands.nutrition import GenerateNutritionCommand
from fitness_bot.service.models.commands.program import (
    ApproveProposalCommand,
    GenerateNextWeekCommand,
    ProposeProgramCommand,
)
from fitness_bot.service.models.commands.session import (
    FinalizeSessionCommand,
    GenerateNextSessionCommand,
    StartSessionFromTemplateCommand,
)
from fitness_bot.service.models.commands.users import EnsureUserCommand, SetGoalCommand, UpdateProfileCommand
from fitness_bot.service.models.queries.nutrition import GetNutritionQuery
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
    weekday = _today_weekday()
    other = 1 if weekday != 1 else 2
    third = next(d for d in range(1, 8) if d not in {weekday, other})
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
                    "weekday": third,
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
    return json.dumps(payload, ensure_ascii=False)


def _next_session_json(*, weight_kg: float = 65) -> str:
    weekday = _today_weekday()
    payload = {
        "document": {
            "program_type": "full_body",
            "days": [
                {
                    "weekday": weekday,
                    "title": "Сегодня+",
                    "position": 1,
                    "slots": [
                        {
                            "position": 1,
                            "exercise_id": str(EX_A),
                            "custom_request": None,
                            "muscle_group": None,
                            "sets": 4,
                            "reps": 8,
                            "duration_seconds": None,
                            "weight_kg": weight_kg,
                            "rest_seconds": 90,
                            "rpe": 8,
                            "technique_note": "",
                        },
                    ],
                },
            ],
        },
        "reply": "Поднял вес по истории.",
    }
    return json.dumps(payload, ensure_ascii=False)


def _nutrition_json() -> str:
    payload = {
        "kcal": 2400,
        "protein_g": 160,
        "fat_g": 70,
        "carb_g": 250,
        "calculation": "Базовый обмен и активность под цель.",
        "meal_regularity": "Три приёма пищи и один перекус.",
        "reply": "Питание посчитано.",
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


async def _activate_program(uow: InMemoryUow) -> None:
    lm = ScriptedLanguageModel([_week_json_for_today()])
    await choose_program_structure_and_style(uow, program_type=ProgramType.FULL_BODY)
    await ProposeProgramCommandHandler(uow, lm, _catalog()).handle(ProposeProgramCommand(telegram_user_id=7))
    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.program_id is not None
    assert approved.nutrition_stale is True


async def test_generate_next_session_then_approve(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program(uow)

    # Complete one session so history is non-empty.
    started = await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )
    await FinalizeSessionCommandHandler(uow).handle(FinalizeSessionCommand(telegram_user_id=7))
    assert started.session_id is not None

    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen == "template"

    lm = ScriptedLanguageModel([_next_session_json(weight_kg=70)])
    draft = await GenerateNextSessionCommandHandler(uow, lm, _catalog()).handle(
        GenerateNextSessionCommand(telegram_user_id=7),
    )
    assert draft.proposal_id is not None
    assert draft.document is not None
    assert draft.document.days[0].slots[0].weight_kg == 70
    assert lm.calls == 1

    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.kind == ProposalKind.NEXT_SESSION

    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.session_id is not None
    assert approved.document is not None
    assert approved.document.days[0].slots[0].weight_kg == 70

    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen == "session"
    assert today.session_status == SessionStatus.IN_PROGRESS
    assert today.document is not None
    assert today.document.days[0].slots[0].weight_kg == 70


async def test_generate_next_session_agent_unavailable(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program(uow)
    lm = ScriptedLanguageModel(fail=AgentUnavailable("down"))
    result = await GenerateNextSessionCommandHandler(uow, lm, _catalog()).handle(
        GenerateNextSessionCommand(telegram_user_id=7),
    )
    assert result.agent_unavailable is True
    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.proposal_id is None


async def test_nutrition_generate_once_then_reuse_and_stale_on_goal(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program(uow)

    status = await GetNutritionQueryHandler(uow).handle(GetNutritionQuery(telegram_user_id=7))
    assert status.status == "stale"

    lm = ScriptedLanguageModel([_nutrition_json()])
    first = await GenerateNutritionCommandHandler(uow, lm).handle(GenerateNutritionCommand(telegram_user_id=7))
    assert first.recommendation_id is not None
    assert first.kcal == 2400
    assert first.already_current is False
    assert lm.calls == 1

    status = await GetNutritionQueryHandler(uow).handle(GetNutritionQuery(telegram_user_id=7))
    assert status.status == "current"
    assert status.kcal == 2400

    second = await GenerateNutritionCommandHandler(uow, lm).handle(GenerateNutritionCommand(telegram_user_id=7))
    assert second.already_current is True
    assert second.recommendation_id == first.recommendation_id
    assert lm.calls == 1

    await SetGoalCommandHandler(uow).handle(SetGoalCommand(telegram_user_id=7, goal=Goal.FAT_LOSS))
    status = await GetNutritionQueryHandler(uow).handle(GetNutritionQuery(telegram_user_id=7))
    assert status.status == "stale"

    lm2 = ScriptedLanguageModel(
        [
            json.dumps(
                {
                    "kcal": 2000,
                    "protein_g": 140,
                    "fat_g": 60,
                    "carb_g": 180,
                    "calculation": "Дефицит под похудение.",
                    "meal_regularity": "Три приёма пищи.",
                    "reply": "Пересчитал.",
                },
                ensure_ascii=False,
            ),
        ],
    )
    regen = await GenerateNutritionCommandHandler(uow, lm2).handle(GenerateNutritionCommand(telegram_user_id=7))
    assert regen.kcal == 2000
    assert regen.already_current is False
    status = await GetNutritionQueryHandler(uow).handle(GetNutritionQuery(telegram_user_id=7))
    assert status.status == "current"
    assert status.kcal == 2000


async def test_nutrition_without_program(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    status = await GetNutritionQueryHandler(uow).handle(GetNutritionQuery(telegram_user_id=7))
    assert status.status == "no_program"


async def test_coach_can_view_client_nutrition(uow: InMemoryUow) -> None:
    from fitness_bot.service.authz import AuthorizationError
    from fitness_bot.service.handlers.commands.coach import (
        AcceptCoachInviteCommandHandler,
        ApproveCoachApplicationCommandHandler,
        CreateCoachInviteCommandHandler,
        SubmitCoachApplicationCommandHandler,
    )
    from fitness_bot.service.models.commands.coach import (
        AcceptCoachInviteCommand,
        ApproveCoachApplicationCommand,
        CreateCoachInviteCommand,
        SubmitCoachApplicationCommand,
    )

    await _seed_profile(uow, telegram_user_id=7)
    await _activate_program(uow)
    lm = ScriptedLanguageModel([_nutrition_json()])
    generated = await GenerateNutritionCommandHandler(uow, lm).handle(GenerateNutritionCommand(telegram_user_id=7))
    assert generated.kcal == 2400

    await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=1, chat_id=1))
    async with uow.transaction() as repos:
        mod = await repos.users.get_by_telegram_id(1)
        assert mod is not None
        mod.is_moderator = True
        await repos.users.save(mod)
    await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=11, chat_id=11))
    await SubmitCoachApplicationCommandHandler(uow).handle(
        SubmitCoachApplicationCommand(
            telegram_user_id=11,
            display_name="Coach",
            bio="bio",
            portfolio_url="https://example.com",
            credential_object_key="k",
            credential_content_type="image/png",
            credential_byte_size=1,
        ),
    )
    async with uow.transaction() as repos:
        app_id = (await repos.coaches.list_pending_applications())[0].id
        client = await repos.users.get_by_telegram_id(7)
        assert client is not None
        client_id = client.id
    await ApproveCoachApplicationCommandHandler(uow).handle(
        ApproveCoachApplicationCommand(telegram_user_id=1, application_id=app_id),
    )
    invite = await CreateCoachInviteCommandHandler(uow).handle(CreateCoachInviteCommand(telegram_user_id=11))
    await AcceptCoachInviteCommandHandler(uow).handle(
        AcceptCoachInviteCommand(telegram_user_id=7, code=invite.code),
    )

    viewed = await GetNutritionQueryHandler(uow).handle(
        GetNutritionQuery(telegram_user_id=11, subject_user_id=client_id),
    )
    assert viewed.status == "current"
    assert viewed.kcal == 2400
    assert viewed.protein_g == 160

    await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=99, chat_id=99))
    with pytest.raises(AuthorizationError):
        await GetNutritionQueryHandler(uow).handle(
            GetNutritionQuery(telegram_user_id=99, subject_user_id=client_id),
        )


def _next_week_json(*, weight_kg: float = 70) -> str:
    weekday = _today_weekday()
    other = 1 if weekday != 1 else 2
    third = next(d for d in range(1, 8) if d not in {weekday, other})
    payload = {
        "document": {
            "program_type": "full_body",
            "days": [
                {
                    "weekday": weekday,
                    "title": "Сегодня+",
                    "position": 1,
                    "slots": [
                        {
                            "position": 1,
                            "exercise_id": str(EX_A),
                            "custom_request": None,
                            "muscle_group": None,
                            "sets": 4,
                            "reps": 8,
                            "duration_seconds": None,
                            "weight_kg": weight_kg,
                            "rest_seconds": 90,
                            "rpe": 8,
                            "technique_note": "",
                        },
                    ],
                },
                {
                    "weekday": other,
                    "title": "Другой+",
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
                            "weight_kg": 55,
                            "rest_seconds": 90,
                            "rpe": 7,
                            "technique_note": "",
                        },
                    ],
                },
                {
                    "weekday": third,
                    "title": "Третий+",
                    "position": 3,
                    "slots": [
                        {
                            "position": 1,
                            "exercise_id": str(EX_B),
                            "custom_request": None,
                            "muscle_group": None,
                            "sets": 3,
                            "reps": 12,
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
        "reply": "Поднял веса по истории.",
    }
    return json.dumps(payload, ensure_ascii=False)


async def _seed_completed_weekdays(uow: InMemoryUow, *, telegram_user_id: int = 7) -> list[int]:
    from fitness_bot.domain.workout.session import Session

    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(telegram_user_id)
        assert user is not None
        assert user.active_program_id is not None
        program = await repos.programs.get_by_id(user.active_program_id)
        assert program is not None
        # Backdate activation so every planned weekday can fall in the past week.
        activated_at = datetime.now(UTC).replace(microsecond=0) - timedelta(days=7)
        program.activated_at = activated_at
        await repos.programs.save(program)
        planned = sorted({day.weekday for day in program.days if day.weekday is not None})
        now = datetime.now(UTC)
        for weekday in planned:
            day = next(item for item in program.days if item.weekday == weekday)
            completed_at = None
            for delta in range(0, 8):
                candidate = (now - timedelta(days=delta)).replace(hour=12, minute=0, second=0, microsecond=0)
                if candidate > now:
                    candidate = now - timedelta(minutes=5)
                if candidate < activated_at:
                    continue
                if local_calendar_date(now=candidate, timezone_offset=user.timezone_offset).isoweekday() == weekday:
                    completed_at = candidate
                    break
            assert completed_at is not None
            session = Session.from_template_day(
                user_id=user.id,
                program_type=program.program_type,
                day=day,
                now=completed_at,
            )
            session.finalize(now=completed_at)
            await repos.sessions.add(session)
        return planned


async def test_generate_next_week_then_approve_resets_progress(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program(uow)
    planned = await _seed_completed_weekdays(uow)

    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen in {"template", "rest"}
    assert today.planned_weekdays == planned
    assert set(today.completed_weekdays) == set(planned)
    assert today.week_finished is True

    old_program_id = today.program_id
    assert old_program_id is not None

    lm = ScriptedLanguageModel([_next_week_json(weight_kg=72)])
    draft = await GenerateNextWeekCommandHandler(uow, lm, _catalog()).handle(
        GenerateNextWeekCommand(telegram_user_id=7),
    )
    assert draft.proposal_id is not None
    assert draft.document is not None
    assert len(draft.document.days) == 3
    assert draft.document.days[0].slots[0].weight_kg == 72
    assert lm.calls == 1

    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.kind == ProposalKind.PROGRAM

    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.program_id is not None
    assert approved.program_id != old_program_id
    assert approved.document is not None
    assert approved.document.days[0].slots[0].weight_kg == 72

    async with uow.transaction() as repos:
        archived = await repos.programs.get_by_id(old_program_id)
        assert archived is not None
        assert archived.status.value == "archived"

    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.program_id == approved.program_id
    assert today.completed_weekdays == []
    assert today.week_finished is False
    assert today.planned_weekdays == planned


async def test_after_next_week_approve_next_session_and_template_still_work(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    await _activate_program(uow)
    await _seed_completed_weekdays(uow)

    lm_week = ScriptedLanguageModel([_next_week_json(weight_kg=68)])
    draft = await GenerateNextWeekCommandHandler(uow, lm_week, _catalog()).handle(
        GenerateNextWeekCommand(telegram_user_id=7),
    )
    assert draft.proposal_id is not None
    await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))

    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen == "template"
    assert today.document is not None

    started = await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )
    assert started.session_id is not None
    await FinalizeSessionCommandHandler(uow).handle(FinalizeSessionCommand(telegram_user_id=7))

    lm_session = ScriptedLanguageModel([_next_session_json(weight_kg=75)])
    next_session = await GenerateNextSessionCommandHandler(uow, lm_session, _catalog()).handle(
        GenerateNextSessionCommand(telegram_user_id=7),
    )
    assert next_session.proposal_id is not None
    pending = await GetPendingProposalQueryHandler(uow).handle(GetPendingProposalQuery(telegram_user_id=7))
    assert pending.kind == ProposalKind.NEXT_SESSION

    approved = await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    assert approved.session_id is not None
    today = await GetTodayWorkoutQueryHandler(uow).handle(GetTodayWorkoutQuery(telegram_user_id=7))
    assert today.screen == "session"
    assert today.session_status == SessionStatus.IN_PROGRESS
