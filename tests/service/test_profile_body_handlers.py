from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal

import pytest

from fitness_bot.domain.body.measurement import FIXED_MEASUREMENT_SITES, MeasurementEntry, MeasurementSite
from fitness_bot.domain.body.reminder import DEFAULT_WEIGHT_REMINDER_TIME, DEFAULT_WEIGHT_REMINDER_WEEKDAYS
from fitness_bot.domain.enums import ExpectedInput, Goal, ProfileField, Sex, WeightSource
from fitness_bot.infrastructure.uow.in_memory import InMemoryUow
from fitness_bot.service.handlers.commands.body import (
    AddCustomMeasurementSiteCommandHandler,
    EnsureDefaultWeightReminderCommandHandler,
    EnsureFixedMeasurementSitesCommandHandler,
    MarkWeightReminderSentCommandHandler,
    RecordMeasurementCommandHandler,
    RecordWeightCommandHandler,
    SeedMeasurementGuidesCommandHandler,
    SetWeightReminderCommandHandler,
)
from fitness_bot.service.handlers.commands.users import (
    EnsureUserCommandHandler,
    ExpectInputCommandHandler,
    SetGoalCommandHandler,
    UpdateProfileCommandHandler,
)
from fitness_bot.service.handlers.queries.body import (
    GetMeasurementGuideQueryHandler,
    GetMeasurementHistoryQueryHandler,
    GetWeightHistoryQueryHandler,
    GetWeightReminderQueryHandler,
    ListDueWeightRemindersQueryHandler,
)
from fitness_bot.service.handlers.queries.users import GetProfileQueryHandler, GetWorkflowQueryHandler
from fitness_bot.service.models.commands.body import (
    AddCustomMeasurementSiteCommand,
    EnsureDefaultWeightReminderCommand,
    EnsureFixedMeasurementSitesCommand,
    MarkWeightReminderSentCommand,
    RecordMeasurementCommand,
    RecordWeightCommand,
    SeedMeasurementGuidesCommand,
    SetWeightReminderCommand,
)
from fitness_bot.service.models.commands.users import (
    EnsureUserCommand,
    ExpectInputCommand,
    SetGoalCommand,
    UpdateProfileCommand,
)
from fitness_bot.service.models.queries.body import (
    GetMeasurementGuideQuery,
    GetMeasurementHistoryQuery,
    GetWeightHistoryQuery,
    GetWeightReminderQuery,
    ListDueWeightRemindersQuery,
)
from fitness_bot.service.models.queries.users import GetProfileQuery, GetWorkflowQuery


class FakeLanguageModel:
    async def complete(self, *, system: str, user: str) -> str:
        _ = system, user
        return '{"instruction":"Ленту держи горизонтально на указанной точке. Одно число в сантиметрах."}'


@pytest.fixture
def uow() -> InMemoryUow:
    return InMemoryUow()


async def _ensure(uow: InMemoryUow, telegram_user_id: int = 42) -> None:
    await EnsureUserCommandHandler(uow).handle(
        EnsureUserCommand(telegram_user_id=telegram_user_id, chat_id=100),
    )


async def test_ensure_user_is_idempotent(uow: InMemoryUow) -> None:
    first = await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=1, chat_id=10))
    second = await EnsureUserCommandHandler(uow).handle(EnsureUserCommand(telegram_user_id=1, chat_id=11))
    assert first.created is True
    assert second.created is False
    assert first.user_id == second.user_id
    profile = await GetProfileQueryHandler(uow).handle(GetProfileQuery(telegram_user_id=1))
    assert profile.chat_id == 11
    reminder = await GetWeightReminderQueryHandler(uow).handle(GetWeightReminderQuery(telegram_user_id=1))
    assert reminder.weekdays == sorted(DEFAULT_WEIGHT_REMINDER_WEEKDAYS)
    assert reminder.local_time == DEFAULT_WEIGHT_REMINDER_TIME


async def test_default_weight_reminder_can_be_customized(uow: InMemoryUow) -> None:
    await _ensure(uow)
    ensured = await EnsureDefaultWeightReminderCommandHandler(uow).handle(
        EnsureDefaultWeightReminderCommand(telegram_user_id=42),
    )
    assert ensured.created is False
    assert ensured.weekdays == [7]
    await SetWeightReminderCommandHandler(uow).handle(
        SetWeightReminderCommand(
            telegram_user_id=42,
            local_time=time(8, 0),
            weekdays=[1, 4],
        ),
    )
    reminder = await GetWeightReminderQueryHandler(uow).handle(GetWeightReminderQuery(telegram_user_id=42))
    assert reminder.weekdays == [1, 4]
    assert reminder.local_time == time(8, 0)
    again = await EnsureDefaultWeightReminderCommandHandler(uow).handle(
        EnsureDefaultWeightReminderCommand(telegram_user_id=42),
    )
    assert again.created is False
    assert again.weekdays == [1, 4]


async def test_second_start_for_same_telegram_id_succeeds(uow: InMemoryUow) -> None:
    """Returning /start must not fail when the telegram user already exists."""
    handler = EnsureUserCommandHandler(uow)
    first = await handler.handle(EnsureUserCommand(telegram_user_id=1390648719, chat_id=1390648719))
    # Simulate a lost get-or-create race: row already present, ensure still succeeds.
    async with uow.transaction() as repos:
        raced, created = await repos.users.ensure(telegram_user_id=1390648719, chat_id=1390648719)
    third = await handler.handle(EnsureUserCommand(telegram_user_id=1390648719, chat_id=42))
    assert first.created is True
    assert created is False
    assert raced.id == first.user_id
    assert third.created is False
    assert third.user_id == first.user_id
    profile = await GetProfileQueryHandler(uow).handle(GetProfileQuery(telegram_user_id=1390648719))
    assert profile.chat_id == 42


async def test_onboarding_weight_and_goal(uow: InMemoryUow) -> None:
    await _ensure(uow)
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.SEX, value=Sex.MALE.value),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.BIRTH_YEAR, value=1990),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.HEIGHT, value="180"),
    )
    await RecordWeightCommandHandler(uow).handle(
        RecordWeightCommand(telegram_user_id=42, kilograms="75.5", source=WeightSource.ONBOARDING),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.EXPERIENCE, value="beginner"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.DAYS_PER_WEEK, value=3),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.TRAINING_WEEKDAYS, value=[1, 3, 5]),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.EQUIPMENT, value="гантели"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.LIMITATIONS, value=""),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.ACTIVITY_LEVEL, value="moderate"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.SESSION_MINUTES, value=60),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.BODY_FAT, value="unknown"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.SUPPLEMENTS, value=["none"]),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.DIET_PREFS, value=""),
    )
    profile = await GetProfileQueryHandler(uow).handle(GetProfileQuery(telegram_user_id=42))
    assert profile.next_field is None
    assert profile.profile_complete is False
    assert profile.weight_kg == Decimal("75.5")
    await SetGoalCommandHandler(uow).handle(SetGoalCommand(telegram_user_id=42, goal=Goal.STRENGTH))
    profile = await GetProfileQueryHandler(uow).handle(GetProfileQuery(telegram_user_id=42))
    assert profile.profile_complete is True
    assert profile.goal == Goal.STRENGTH
    assert profile.nutrition_stale is True


async def test_weight_same_local_day_keeps_latest_only(uow: InMemoryUow) -> None:
    await _ensure(uow)
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(42)
        assert user is not None
        user.timezone_offset = "+03:00"
        await repos.users.save(user)

    morning = datetime(2026, 9, 22, 6, 0, tzinfo=UTC)  # 09:00 local
    evening = datetime(2026, 9, 22, 18, 0, tzinfo=UTC)  # 21:00 local
    first = await RecordWeightCommandHandler(uow).handle(
        RecordWeightCommand(
            telegram_user_id=42,
            kilograms="80",
            source=WeightSource.MANUAL,
            measured_at=morning,
        ),
    )
    second = await RecordWeightCommandHandler(uow).handle(
        RecordWeightCommand(
            telegram_user_id=42,
            kilograms="81.2",
            source=WeightSource.MANUAL,
            measured_at=evening,
        ),
    )
    assert first.entry_id == second.entry_id
    assert second.kilograms == Decimal("81.2")

    history = await GetWeightHistoryQueryHandler(uow).handle(GetWeightHistoryQuery(telegram_user_id=42))
    assert len(history.items) == 1
    assert history.items[0].kilograms == Decimal("81.2")
    assert history.items[0].measured_on.isoformat() == "2026-09-22"
    assert history.latest_kg == Decimal("81.2")


async def test_weight_next_local_day_creates_new_entry(uow: InMemoryUow) -> None:
    await _ensure(uow)
    day1 = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    day2 = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    first = await RecordWeightCommandHandler(uow).handle(
        RecordWeightCommand(
            telegram_user_id=42,
            kilograms="80",
            source=WeightSource.MANUAL,
            measured_at=day1,
        ),
    )
    second = await RecordWeightCommandHandler(uow).handle(
        RecordWeightCommand(
            telegram_user_id=42,
            kilograms="79.5",
            source=WeightSource.MANUAL,
            measured_at=day2,
        ),
    )
    assert first.entry_id != second.entry_id
    history = await GetWeightHistoryQueryHandler(uow).handle(GetWeightHistoryQuery(telegram_user_id=42))
    assert [item.kilograms for item in history.items] == [Decimal("79.5"), Decimal("80")]
    assert [item.measured_on.isoformat() for item in history.items] == ["2026-09-23", "2026-09-22"]


async def test_weight_reminder_due_and_busy_dialog(uow: InMemoryUow) -> None:
    await _ensure(uow)
    await ExpectInputCommandHandler(uow).handle(
        ExpectInputCommand(telegram_user_id=42, expected_input=ExpectedInput.NONE),
    )
    await SetWeightReminderCommandHandler(uow).handle(
        SetWeightReminderCommand(
            telegram_user_id=42,
            local_time=time(8, 30),
            weekdays=[1, 2, 3, 4, 5, 6, 7],
        ),
    )
    now = datetime(2026, 9, 22, 8, 30, tzinfo=UTC)  # Tuesday
    due = await ListDueWeightRemindersQueryHandler(uow).handle(ListDueWeightRemindersQuery(now=now))
    assert len(due.items) == 1
    await ExpectInputCommandHandler(uow).handle(
        ExpectInputCommand(telegram_user_id=42, expected_input=ExpectedInput.WEIGHT),
    )
    due_busy = await ListDueWeightRemindersQueryHandler(uow).handle(ListDueWeightRemindersQuery(now=now))
    assert due_busy.items == []
    await ExpectInputCommandHandler(uow).handle(
        ExpectInputCommand(telegram_user_id=42, expected_input=ExpectedInput.NONE),
    )
    await MarkWeightReminderSentCommandHandler(uow).handle(
        MarkWeightReminderSentCommand(user_id=due.items[0].user_id, sent_on=due.items[0].local_date),
    )
    due_again = await ListDueWeightRemindersQueryHandler(uow).handle(ListDueWeightRemindersQuery(now=now))
    assert due_again.items == []


async def test_measurement_flow(uow: InMemoryUow) -> None:
    await _ensure(uow)
    site = MeasurementSite.fixed("waist", "Талия")
    async with uow.transaction() as repos:
        await repos.measurements.add_site(site)
    await ExpectInputCommandHandler(uow).handle(
        ExpectInputCommand(
            telegram_user_id=42,
            expected_input=ExpectedInput.MEASUREMENT_VALUE,
            pending_site_id=site.id,
        ),
    )
    await RecordMeasurementCommandHandler(uow).handle(
        RecordMeasurementCommand(telegram_user_id=42, site_id=site.id, centimeters="80.5"),
    )
    workflow = await GetWorkflowQueryHandler(uow).handle(GetWorkflowQuery(telegram_user_id=42))
    assert workflow.expected_input == ExpectedInput.NONE
    custom = await AddCustomMeasurementSiteCommandHandler(uow).handle(
        AddCustomMeasurementSiteCommand(telegram_user_id=42, name="Бицепс левый"),
    )
    workflow = await GetWorkflowQueryHandler(uow).handle(GetWorkflowQuery(telegram_user_id=42))
    assert workflow.expected_input == ExpectedInput.MEASUREMENT_VALUE
    assert workflow.pending_site_id == custom.site_id


async def test_seed_measurement_guides(uow: InMemoryUow) -> None:
    handler = SeedMeasurementGuidesCommandHandler(uow, FakeLanguageModel())
    first = await handler.handle(SeedMeasurementGuidesCommand())
    second = await handler.handle(SeedMeasurementGuidesCommand())
    assert first.seeded == len(FIXED_MEASUREMENT_SITES)
    assert second.seeded == 0
    assert second.skipped == len(FIXED_MEASUREMENT_SITES)


async def test_ensure_fixed_measurement_sites_for_menu(uow: InMemoryUow) -> None:
    await _ensure(uow)
    first = await EnsureFixedMeasurementSitesCommandHandler(uow).handle(EnsureFixedMeasurementSitesCommand())
    assert first.sites_created == len(FIXED_MEASUREMENT_SITES)
    assert first.guides_created == len(FIXED_MEASUREMENT_SITES)
    second = await EnsureFixedMeasurementSitesCommandHandler(uow).handle(EnsureFixedMeasurementSitesCommand())
    assert second.sites_created == 0
    assert second.guides_created == 0
    history = await GetMeasurementHistoryQueryHandler(uow).handle(
        GetMeasurementHistoryQuery(telegram_user_id=42),
    )
    assert len(history.sites) == len(FIXED_MEASUREMENT_SITES)
    assert [site.name for site in history.sites] == sorted(name for _, name in FIXED_MEASUREMENT_SITES)
    waist = next(site for site in history.sites if site.code == "waist")
    guide = await GetMeasurementGuideQueryHandler(uow).handle(GetMeasurementGuideQuery(site_id=waist.id))
    assert guide.site_code == "waist"
    assert guide.instruction is not None
    assert "лент" in guide.instruction.lower()


async def test_profile_payload_includes_new_fields_and_circumferences(uow: InMemoryUow) -> None:
    await _ensure(uow)
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.SEX, value=Sex.MALE.value),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.EXPERIENCE, value="advanced"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.ACTIVITY_LEVEL, value="high"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.SESSION_MINUTES, value=90),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.BODY_FAT, value="unknown"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(
            telegram_user_id=42,
            field=ProfileField.SUPPLEMENTS,
            value={"codes": ["protein", "other"], "other": "HMB"},
        ),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.DIET_PREFS, value="без лактозы"),
    )
    await UpdateProfileCommandHandler(uow).handle(
        UpdateProfileCommand(telegram_user_id=42, field=ProfileField.PHARMA, value=""),
    )
    site = MeasurementSite.fixed("neck", "Шея")
    async with uow.transaction() as repos:
        user = await repos.users.get_by_telegram_id(42)
        assert user is not None
        await repos.measurements.add_site(site)
        await repos.measurements.add_entry(
            MeasurementEntry.create(
                user_id=user.id,
                site_id=site.id,
                centimeters="38",
                measured_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
            ),
        )
        from fitness_bot.service.handlers.commands.program import build_profile_payload

        payload = await build_profile_payload(repos, user, weight_kg=Decimal("80"))
    assert payload["experience"] == "advanced"
    assert payload["activity_level"] == "high"
    assert payload["session_minutes"] == 90
    assert payload["body_fat_unknown"] is True
    assert payload["body_fat_pct"] is None
    assert payload["supplements"] == ["other", "protein"]
    assert payload["supplements_other"] == "HMB"
    assert payload["diet_prefs"] == "без лактозы"
    assert payload["pharma"] == ""
    assert payload["circumferences_cm"]["neck"] == "38"
    from fitness_bot.domain.users.user import PROFILE_FIELD_ORDER

    assert ProfileField.PHARMA not in PROFILE_FIELD_ORDER
