from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fitness_bot.domain.enums import (
    ExpectedInput,
    Goal,
    ProfileField,
    ProgramType,
    Sex,
    WeightSource,
)
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import local_calendar_date
from fitness_bot.infrastructure.adapters.object_storage import InMemoryObjectStorage
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.body import RecordWeightCommandHandler
from fitness_bot.service.handlers.commands.program import (
    ApproveProposalCommandHandler,
    ProposeProgramCommandHandler,
)
from fitness_bot.service.handlers.commands.session import (
    ConfirmExerciseAsPlannedCommandHandler,
    FinalizeSessionCommandHandler,
    RememberTechniqueVideoFileIdCommandHandler,
    SaveTechniqueVideoCommandHandler,
    StartSessionFromTemplateCommandHandler,
)
from fitness_bot.service.handlers.commands.users import (
    EnsureUserCommandHandler,
    ExpectInputCommandHandler,
    SetGoalCommandHandler,
    UpdateProfileCommandHandler,
)
from fitness_bot.service.handlers.queries.session import (
    GetSessionDetailQueryHandler,
    GetSessionHistoryQueryHandler,
    PrepareTechniqueVideoDeliveryQueryHandler,
)
from fitness_bot.service.models.commands.body import RecordWeightCommand
from fitness_bot.service.models.commands.program import (
    ApproveProposalCommand,
    ProposeProgramCommand,
)
from fitness_bot.service.models.commands.session import (
    ConfirmExerciseAsPlannedCommand,
    FinalizeSessionCommand,
    RememberTechniqueVideoFileIdCommand,
    SaveTechniqueVideoCommand,
    StartSessionFromTemplateCommand,
)
from fitness_bot.service.models.commands.users import (
    EnsureUserCommand,
    ExpectInputCommand,
    SetGoalCommand,
    UpdateProfileCommand,
)
from fitness_bot.service.models.queries.session import (
    GetSessionDetailQuery,
    GetSessionHistoryQuery,
    PrepareTechniqueVideoDeliveryQuery,
)
from fitness_bot.service.ports.exercise_catalog import InMemoryExerciseCatalog, record
from tests.support.program_flow import choose_program_structure_and_style

EX_A = uuid4()
EX_B = uuid4()


class ScriptedLanguageModel:
    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or [])

    async def complete(self, *, system: str, user: str) -> str:
        _ = system, user
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


async def _bootstrap_open_session_with_fact(uow: InMemoryUow) -> None:
    await _seed_profile(uow)
    lm = ScriptedLanguageModel([_week_json_for_today()])
    await choose_program_structure_and_style(uow, program_type=ProgramType.FULL_BODY)
    await ProposeProgramCommandHandler(uow, lm, _catalog()).handle(ProposeProgramCommand(telegram_user_id=7))
    await ApproveProposalCommandHandler(uow).handle(ApproveProposalCommand(telegram_user_id=7))
    await StartSessionFromTemplateCommandHandler(uow, InMemoryObjectStorage()).handle(
        StartSessionFromTemplateCommand(telegram_user_id=7),
    )
    await ConfirmExerciseAsPlannedCommandHandler(uow).handle(
        ConfirmExerciseAsPlannedCommand(telegram_user_id=7, slot_position=1),
    )


@pytest.mark.asyncio
async def test_save_technique_video_stores_bytes_and_replaces() -> None:
    uow = InMemoryUow()
    storage = InMemoryObjectStorage()
    await _bootstrap_open_session_with_fact(uow)

    await ExpectInputCommandHandler(uow).handle(
        ExpectInputCommand(
            telegram_user_id=7,
            expected_input=ExpectedInput.TECHNIQUE_VIDEO,
            focus_slot=1,
        ),
    )
    handler = SaveTechniqueVideoCommandHandler(uow, storage)
    first = await handler.handle(
        SaveTechniqueVideoCommand(
            telegram_user_id=7,
            body=b"video-one",
            content_type="video/mp4",
        ),
    )
    assert first.replaced is False
    assert await storage.get(first.object_key) == b"video-one"

    await ExpectInputCommandHandler(uow).handle(
        ExpectInputCommand(
            telegram_user_id=7,
            expected_input=ExpectedInput.TECHNIQUE_VIDEO,
            focus_slot=1,
        ),
    )
    second = await handler.handle(
        SaveTechniqueVideoCommand(
            telegram_user_id=7,
            body=b"video-two",
            content_type="video/mp4",
        ),
    )
    assert second.replaced is True
    assert second.slot_id == first.slot_id
    assert await storage.get(second.object_key) == b"video-two"

    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(7)
        assert user is not None
        assert user.expected_input == ExpectedInput.NONE
        video = await repos.technique_videos.get_by_slot_id(first.slot_id)
        assert video is not None
        assert video.telegram_file_id is None


@pytest.mark.asyncio
async def test_save_technique_video_rejects_non_video_and_missing_actual() -> None:
    uow = InMemoryUow()
    storage = InMemoryObjectStorage()
    await _bootstrap_open_session_with_fact(uow)
    handler = SaveTechniqueVideoCommandHandler(uow, storage)

    with pytest.raises(DomainError, match="video/"):
        await handler.handle(
            SaveTechniqueVideoCommand(
                telegram_user_id=7,
                body=b"x",
                content_type="image/png",
                slot_position=1,
            ),
        )

    with pytest.raises(DomainError, match="actual"):
        await handler.handle(
            SaveTechniqueVideoCommand(
                telegram_user_id=7,
                body=b"x",
                content_type="video/mp4",
                slot_position=2,
            ),
        )


@pytest.mark.asyncio
async def test_history_delivery_returns_bytes_then_file_id() -> None:
    uow = InMemoryUow()
    storage = InMemoryObjectStorage()
    catalog = _catalog()
    await _bootstrap_open_session_with_fact(uow)

    saved = await SaveTechniqueVideoCommandHandler(uow, storage).handle(
        SaveTechniqueVideoCommand(
            telegram_user_id=7,
            body=b"history-bytes",
            content_type="video/mp4",
            slot_position=1,
        ),
    )
    await FinalizeSessionCommandHandler(uow).handle(FinalizeSessionCommand(telegram_user_id=7))

    history = await GetSessionHistoryQueryHandler(uow).handle(GetSessionHistoryQuery(telegram_user_id=7))
    assert len(history.items) == 1
    detail = await GetSessionDetailQueryHandler(uow, catalog).handle(
        GetSessionDetailQuery(telegram_user_id=7, session_id=history.items[0].session_id),
    )
    assert any(slot.has_technique_video for slot in detail.slots)

    prepare = PrepareTechniqueVideoDeliveryQueryHandler(uow, storage, catalog)
    delivery = await prepare.handle(
        PrepareTechniqueVideoDeliveryQuery(telegram_user_id=7, slot_id=saved.slot_id),
    )
    assert delivery.missing is False
    assert delivery.body == b"history-bytes"
    assert delivery.telegram_file_id is None
    assert "Жим" in delivery.exercise_name

    remembered = await RememberTechniqueVideoFileIdCommandHandler(uow).handle(
        RememberTechniqueVideoFileIdCommand(
            telegram_user_id=7,
            slot_id=saved.slot_id,
            telegram_file_id="tg-file-1",
        ),
    )
    assert remembered.telegram_file_id == "tg-file-1"

    again = await prepare.handle(
        PrepareTechniqueVideoDeliveryQuery(telegram_user_id=7, slot_id=saved.slot_id),
    )
    assert again.telegram_file_id == "tg-file-1"
    assert again.body is None


@pytest.mark.asyncio
async def test_prepare_missing_object_marks_missing() -> None:
    uow = InMemoryUow()
    storage = InMemoryObjectStorage()
    catalog = _catalog()
    await _bootstrap_open_session_with_fact(uow)
    saved = await SaveTechniqueVideoCommandHandler(uow, storage).handle(
        SaveTechniqueVideoCommand(
            telegram_user_id=7,
            body=b"gone",
            content_type="video/mp4",
            slot_position=1,
        ),
    )
    await storage.delete(saved.object_key)
    delivery = await PrepareTechniqueVideoDeliveryQueryHandler(uow, storage, catalog).handle(
        PrepareTechniqueVideoDeliveryQuery(telegram_user_id=7, slot_id=saved.slot_id),
    )
    assert delivery.missing is True
