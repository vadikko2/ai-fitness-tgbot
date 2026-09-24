from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fitness_bot.domain.enums import ExpectedInput, ProgressPhotoAngle
from fitness_bot.domain.errors import DomainError
from fitness_bot.infrastructure.adapters.object_storage import InMemoryObjectStorage
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.authz import AuthorizationError
from fitness_bot.service.handlers.commands.body import (
    CancelProgressPhotoCaptureCommandHandler,
    EnsureDefaultProgressPhotoReminderCommandHandler,
    MarkProgressPhotoReminderSentCommandHandler,
    RecordProgressPhotoCommandHandler,
    StartProgressPhotoCaptureCommandHandler,
)
from fitness_bot.service.handlers.commands.users import EnsureUserCommandHandler
from fitness_bot.service.handlers.queries.body import (
    GetProgressPhotoHistoryQueryHandler,
    GetProgressPhotoSetQueryHandler,
    ListDueProgressPhotoRemindersQueryHandler,
)
from fitness_bot.service.models.commands.body import (
    CancelProgressPhotoCaptureCommand,
    EnsureDefaultProgressPhotoReminderCommand,
    MarkProgressPhotoReminderSentCommand,
    RecordProgressPhotoCommand,
    StartProgressPhotoCaptureCommand,
)
from fitness_bot.service.models.commands.users import EnsureUserCommand
from fitness_bot.service.models.queries.body import (
    GetProgressPhotoHistoryQuery,
    GetProgressPhotoSetQuery,
    ListDueProgressPhotoRemindersQuery,
)


@pytest.fixture
def uow() -> InMemoryUow:
    return InMemoryUow()


@pytest.fixture
def storage() -> InMemoryObjectStorage:
    return InMemoryObjectStorage()


async def _ensure(uow: InMemoryUow, telegram_user_id: int = 42, chat_id: int = 100) -> None:
    await EnsureUserCommandHandler(uow).handle(
        EnsureUserCommand(telegram_user_id=telegram_user_id, chat_id=chat_id),
    )


async def test_progress_photo_capture_sequence(uow: InMemoryUow, storage: InMemoryObjectStorage) -> None:
    await _ensure(uow)
    start = await StartProgressPhotoCaptureCommandHandler(uow).handle(
        StartProgressPhotoCaptureCommand(telegram_user_id=42),
    )
    assert start.next_angle == ProgressPhotoAngle.FRONT.value
    assert start.resumed is False

    record = RecordProgressPhotoCommandHandler(uow, storage)
    first = await record.handle(
        RecordProgressPhotoCommand(
            telegram_user_id=42,
            body=b"front",
            content_type="image/jpeg",
        ),
    )
    assert first.angle == "front"
    assert first.next_angle == "side"
    assert first.complete is False

    second = await record.handle(
        RecordProgressPhotoCommand(telegram_user_id=42, body=b"side", content_type="image/jpeg"),
    )
    assert second.next_angle == "back"

    third = await record.handle(
        RecordProgressPhotoCommand(telegram_user_id=42, body=b"back", content_type="image/jpeg"),
    )
    assert third.complete is True
    assert third.next_angle is None

    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(42)
        assert user is not None
        assert user.expected_input == ExpectedInput.NONE
        photo_set = await repos.progress_photos.get_set(start.set_id)
        assert photo_set is not None
        assert photo_set.complete
        assert len(photo_set.photos) == 3


async def test_progress_photo_same_day_replace_angle(uow: InMemoryUow, storage: InMemoryObjectStorage) -> None:
    await _ensure(uow)
    record = RecordProgressPhotoCommandHandler(uow, storage)
    start = await StartProgressPhotoCaptureCommandHandler(uow).handle(
        StartProgressPhotoCaptureCommand(telegram_user_id=42),
    )
    await record.handle(RecordProgressPhotoCommand(telegram_user_id=42, body=b"a", content_type="image/jpeg"))
    await record.handle(RecordProgressPhotoCommand(telegram_user_id=42, body=b"b", content_type="image/jpeg"))
    await record.handle(RecordProgressPhotoCommand(telegram_user_id=42, body=b"c", content_type="image/jpeg"))

    again = await StartProgressPhotoCaptureCommandHandler(uow).handle(
        StartProgressPhotoCaptureCommand(telegram_user_id=42),
    )
    assert again.set_id == start.set_id
    assert again.next_angle == "front"
    # Retake clears prior angles, then records fresh front → side → back.
    first = await record.handle(
        RecordProgressPhotoCommand(telegram_user_id=42, body=b"front2", content_type="image/jpeg"),
    )
    assert first.replaced is False
    assert first.next_angle == "side"

    # Mid-set replace of the same angle does mark replaced.
    again_front = await record.handle(
        RecordProgressPhotoCommand(
            telegram_user_id=42,
            body=b"front3",
            content_type="image/jpeg",
            angle="front",
        ),
    )
    assert again_front.replaced is True
    assert again_front.next_angle == "side"


async def test_cancel_progress_photo_keeps_incomplete_set(uow: InMemoryUow, storage: InMemoryObjectStorage) -> None:
    await _ensure(uow)
    start = await StartProgressPhotoCaptureCommandHandler(uow).handle(
        StartProgressPhotoCaptureCommand(telegram_user_id=42),
    )
    await RecordProgressPhotoCommandHandler(uow, storage).handle(
        RecordProgressPhotoCommand(telegram_user_id=42, body=b"front", content_type="image/jpeg"),
    )
    cancel = await CancelProgressPhotoCaptureCommandHandler(uow).handle(
        CancelProgressPhotoCaptureCommand(telegram_user_id=42),
    )
    assert cancel.cleared is True
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(42)
        assert user is not None
        assert user.expected_input == ExpectedInput.NONE
        photo_set = await repos.progress_photos.get_set(start.set_id)
        assert photo_set is not None
        assert not photo_set.complete
        assert len(photo_set.photos) == 1


async def test_progress_photo_reminder_due_skips_busy(uow: InMemoryUow) -> None:
    await _ensure(uow)
    await EnsureDefaultProgressPhotoReminderCommandHandler(uow).handle(
        EnsureDefaultProgressPhotoReminderCommand(telegram_user_id=42),
    )
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(42)
        assert user is not None
        user.timezone_offset = "+00:00"
        user.expect_input(ExpectedInput.WEIGHT)
        await repos.users.save(user)
        reminder = await repos.progress_photo_reminders.get(user.id)
        assert reminder is not None
        user_id = user.id

    now = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)  # Sunday
    due = await ListDueProgressPhotoRemindersQueryHandler(uow).handle(
        ListDueProgressPhotoRemindersQuery(now=now),
    )
    assert due.items == []

    async with uow.transaction() as repos:
        user = await repos.users.get_by_id(user_id)
        assert user is not None
        user.clear_expectation()
        await repos.users.save(user)

    due2 = await ListDueProgressPhotoRemindersQueryHandler(uow).handle(
        ListDueProgressPhotoRemindersQuery(now=now),
    )
    assert len(due2.items) == 1
    await MarkProgressPhotoReminderSentCommandHandler(uow).handle(
        MarkProgressPhotoReminderSentCommand(user_id=user_id, sent_on=due2.items[0].local_date),
    )
    due3 = await ListDueProgressPhotoRemindersQueryHandler(uow).handle(
        ListDueProgressPhotoRemindersQuery(now=now),
    )
    assert due3.items == []


async def test_progress_photo_history_coach_authz(uow: InMemoryUow, storage: InMemoryObjectStorage) -> None:
    from fitness_bot.domain.coach.link import CoachClientLink
    from fitness_bot.domain.coach.profile import CoachProfile

    await _ensure(uow, telegram_user_id=1, chat_id=11)
    await _ensure(uow, telegram_user_id=2, chat_id=22)
    await _ensure(uow, telegram_user_id=3, chat_id=33)

    async with uow.transaction() as repos:
        athlete = await repos.users.get_by_telegram_id(1)
        coach = await repos.users.get_by_telegram_id(2)
        stranger = await repos.users.get_by_telegram_id(3)
        assert athlete and coach and stranger
        profile = CoachProfile.create(user_id=coach.id, display_name="Coach")
        profile.mark_verified()
        await repos.coaches.save_profile(profile)
        await repos.coaches.save_link(
            CoachClientLink.activate(coach_user_id=coach.id, client_user_id=athlete.id),
        )
        athlete_id = athlete.id

    await StartProgressPhotoCaptureCommandHandler(uow).handle(
        StartProgressPhotoCaptureCommand(telegram_user_id=1),
    )
    record = RecordProgressPhotoCommandHandler(uow, storage)
    for _ in range(3):
        await record.handle(
            RecordProgressPhotoCommand(telegram_user_id=1, body=b"x", content_type="image/jpeg"),
        )

    history = await GetProgressPhotoHistoryQueryHandler(uow).handle(
        GetProgressPhotoHistoryQuery(telegram_user_id=2, subject_user_id=athlete_id),
    )
    assert len(history.items) == 1
    set_id = history.items[0].set_id

    delivery = await GetProgressPhotoSetQueryHandler(uow, storage).handle(
        GetProgressPhotoSetQuery(telegram_user_id=2, set_id=set_id),
    )
    assert delivery.complete
    assert delivery.subject_user_id == athlete_id
    assert all(item.body is not None for item in delivery.photos)

    with pytest.raises(AuthorizationError):
        await GetProgressPhotoHistoryQueryHandler(uow).handle(
            GetProgressPhotoHistoryQuery(telegram_user_id=3, subject_user_id=athlete_id),
        )

    with pytest.raises(AuthorizationError):
        await GetProgressPhotoSetQueryHandler(uow, storage).handle(
            GetProgressPhotoSetQuery(telegram_user_id=3, set_id=set_id),
        )


async def test_record_rejects_non_image(uow: InMemoryUow, storage: InMemoryObjectStorage) -> None:
    await _ensure(uow)
    await StartProgressPhotoCaptureCommandHandler(uow).handle(
        StartProgressPhotoCaptureCommand(telegram_user_id=42),
    )
    with pytest.raises(DomainError):
        await RecordProgressPhotoCommandHandler(uow, storage).handle(
            RecordProgressPhotoCommand(telegram_user_id=42, body=b"x", content_type="video/mp4"),
        )


async def test_get_home_and_my_coach_linked_fields(uow: InMemoryUow) -> None:
    from fitness_bot.domain.coach.link import CoachClientLink
    from fitness_bot.domain.coach.profile import CoachProfile
    from fitness_bot.service.handlers.queries.coach import GetMyCoachQueryHandler
    from fitness_bot.service.handlers.queries.users import GetHomeQueryHandler
    from fitness_bot.service.models.queries.coach import GetMyCoachQuery
    from fitness_bot.service.models.queries.users import GetHomeQuery

    await _ensure(uow, telegram_user_id=1, chat_id=11)
    await _ensure(uow, telegram_user_id=2, chat_id=22)
    async with uow.transaction() as repos:
        athlete = await repos.users.get_by_telegram_id(1)
        coach = await repos.users.get_by_telegram_id(2)
        assert athlete and coach
        profile = CoachProfile.create(user_id=coach.id, display_name="Иван Тренер", bio="bio")
        profile.mark_verified()
        await repos.coaches.save_profile(profile)
        await repos.coaches.save_link(
            CoachClientLink.activate(coach_user_id=coach.id, client_user_id=athlete.id),
        )
        coach_id = coach.id

    home = await GetHomeQueryHandler(uow).handle(GetHomeQuery(telegram_user_id=1))
    assert home.linked_coach_user_id == coach_id
    assert home.linked_coach_display_name == "Иван Тренер"

    mine = await GetMyCoachQueryHandler(uow).handle(GetMyCoachQuery(telegram_user_id=1))
    assert mine.linked is True
    assert mine.display_name == "Иван Тренер"
    assert mine.bio == "bio"


async def test_ensure_user_seeds_default_progress_photo_reminder(uow: InMemoryUow) -> None:
    await _ensure(uow)
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(42)
        assert user is not None
        reminder = await repos.progress_photo_reminders.get(user.id)
        assert reminder is not None
        assert reminder.weekdays == frozenset({7})
        assert reminder.local_time.hour == 9


async def test_set_progress_photo_reminder(uow: InMemoryUow) -> None:
    from datetime import time

    from fitness_bot.service.handlers.commands.body import SetProgressPhotoReminderCommandHandler
    from fitness_bot.service.models.commands.body import SetProgressPhotoReminderCommand

    await _ensure(uow)
    result = await SetProgressPhotoReminderCommandHandler(uow).handle(
        SetProgressPhotoReminderCommand(
            telegram_user_id=42,
            local_time=time(7, 30),
            weekdays=[1, 3, 5],
        ),
    )
    assert sorted(result.weekdays) == [1, 3, 5]
    assert result.local_time == time(7, 30)
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(42)
        assert user is not None
        reminder = await repos.progress_photo_reminders.get(user.id)
        assert reminder is not None
        assert reminder.weekdays == frozenset({1, 3, 5})
        assert reminder.local_time == time(7, 30)


async def test_athlete_owns_progress_photo_history(uow: InMemoryUow, storage: InMemoryObjectStorage) -> None:
    await _ensure(uow)
    await StartProgressPhotoCaptureCommandHandler(uow).handle(
        StartProgressPhotoCaptureCommand(telegram_user_id=42),
    )
    record = RecordProgressPhotoCommandHandler(uow, storage)
    for _ in range(3):
        await record.handle(
            RecordProgressPhotoCommand(telegram_user_id=42, body=b"x", content_type="image/jpeg"),
        )
    history = await GetProgressPhotoHistoryQueryHandler(uow).handle(
        GetProgressPhotoHistoryQuery(telegram_user_id=42),
    )
    assert len(history.items) == 1
    delivery = await GetProgressPhotoSetQueryHandler(uow, storage).handle(
        GetProgressPhotoSetQuery(telegram_user_id=42, set_id=history.items[0].set_id),
    )
    assert delivery.complete


async def test_remember_progress_photo_file_id(uow: InMemoryUow, storage: InMemoryObjectStorage) -> None:
    from fitness_bot.service.handlers.commands.body import RememberProgressPhotoFileIdCommandHandler
    from fitness_bot.service.models.commands.body import RememberProgressPhotoFileIdCommand

    await _ensure(uow)
    start = await StartProgressPhotoCaptureCommandHandler(uow).handle(
        StartProgressPhotoCaptureCommand(telegram_user_id=42),
    )
    await RecordProgressPhotoCommandHandler(uow, storage).handle(
        RecordProgressPhotoCommand(telegram_user_id=42, body=b"front", content_type="image/jpeg"),
    )
    async with uow.transaction() as repos:
        photo_set = await repos.progress_photos.get_set(start.set_id)
        assert photo_set is not None
        photo_id = photo_set.photos[0].id

    remembered = await RememberProgressPhotoFileIdCommandHandler(uow).handle(
        RememberProgressPhotoFileIdCommand(
            telegram_user_id=42,
            set_id=start.set_id,
            photo_id=photo_id,
            telegram_file_id="tg-file-1",
        ),
    )
    assert remembered.telegram_file_id == "tg-file-1"
    async with uow.transaction() as repos:
        photo_set = await repos.progress_photos.get_set(start.set_id)
        assert photo_set is not None
        assert photo_set.photos[0].telegram_file_id == "tg-file-1"


async def test_progress_photo_set_coach_authz_deny(uow: InMemoryUow, storage: InMemoryObjectStorage) -> None:
    await _ensure(uow, telegram_user_id=1, chat_id=11)
    await _ensure(uow, telegram_user_id=3, chat_id=33)
    await StartProgressPhotoCaptureCommandHandler(uow).handle(
        StartProgressPhotoCaptureCommand(telegram_user_id=1),
    )
    record = RecordProgressPhotoCommandHandler(uow, storage)
    for _ in range(3):
        await record.handle(
            RecordProgressPhotoCommand(telegram_user_id=1, body=b"x", content_type="image/jpeg"),
        )
    history = await GetProgressPhotoHistoryQueryHandler(uow).handle(
        GetProgressPhotoHistoryQuery(telegram_user_id=1),
    )
    set_id = history.items[0].set_id
    async with uow.transaction() as repos:
        athlete = await repos.users.get_by_telegram_id(1)
        assert athlete is not None
        athlete_id = athlete.id

    with pytest.raises(AuthorizationError):
        await GetProgressPhotoSetQueryHandler(uow, storage).handle(
            GetProgressPhotoSetQuery(telegram_user_id=3, set_id=set_id, subject_user_id=athlete_id),
        )
