from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from copy import deepcopy
from datetime import UTC, date, datetime
from uuid import UUID

from fitness_bot.domain.body.measurement import MeasurementEntry, MeasurementGuide, MeasurementSite
from fitness_bot.domain.body.nutrition import NutritionRecommendation
from fitness_bot.domain.body.progress_photo import ProgressPhotoSet
from fitness_bot.domain.body.reminder import ProgressPhotoReminder, WeightReminder
from fitness_bot.domain.body.weight import WeightEntry
from fitness_bot.domain.body.wellbeing import WellbeingEntry
from fitness_bot.domain.enums import Goal
from fitness_bot.domain.users.user import User
from fitness_bot.domain.workout.technique_video import TechniqueVideo
from fitness_bot.infrastructure.uow.in_memory_coach import InMemoryCoachesRepository
from fitness_bot.infrastructure.uow.in_memory_feedback import InMemoryFeedbackRepository
from fitness_bot.infrastructure.uow.in_memory_program import (
    InMemoryProgramsRepository,
    InMemoryProposalsRepository,
    InMemorySessionsRepository,
)
from fitness_bot.service.interfaces.uow import (
    ICoachesRepository,
    IFeedbackRepository,
    IMeasurementRepository,
    INutritionRepository,
    IProgramsRepository,
    IProgressPhotoReminderRepository,
    IProgressPhotoRepository,
    IProposalsRepository,
    ISessionsRepository,
    ITechniqueVideosRepository,
    IUow,
    IUowRepositories,
    IUsersRepository,
    IWeightReminderRepository,
    IWeightRepository,
    IWellbeingRepository,
)


class InMemoryUsersRepository(IUsersRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, User] = {}
        self._by_telegram: dict[int, UUID] = {}

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        user_id = self._by_telegram.get(telegram_user_id)
        if user_id is None:
            return None
        return deepcopy(self._by_id[user_id])

    async def get_by_id(self, user_id: UUID) -> User | None:
        user = self._by_id.get(user_id)
        return deepcopy(user) if user else None

    async def add(self, user: User) -> User:
        if user.telegram_user_id in self._by_telegram:
            return await self.get_by_telegram_id(user.telegram_user_id)  # type: ignore[return-value]
        stored = deepcopy(user)
        self._by_id[stored.id] = stored
        self._by_telegram[stored.telegram_user_id] = stored.id
        return deepcopy(stored)

    async def ensure(self, *, telegram_user_id: int, chat_id: int) -> tuple[User, bool]:
        existing = await self.get_by_telegram_id(telegram_user_id)
        if existing is not None:
            if existing.chat_id != chat_id:
                existing.chat_id = chat_id
                existing.updated_at = datetime.now(UTC)
                existing = await self.save(existing)
            return existing, False
        created = await self.add(User(telegram_user_id=telegram_user_id, chat_id=chat_id))
        return created, True

    async def save(self, user: User) -> User:
        if user.id not in self._by_id:
            raise KeyError(user.id)
        stored = deepcopy(user)
        self._by_id[stored.id] = stored
        self._by_telegram[stored.telegram_user_id] = stored.id
        return deepcopy(stored)

    async def list_with_timezone(self) -> list[User]:
        return [deepcopy(user) for user in self._by_id.values() if user.timezone_offset is not None]

    async def list_moderators(self) -> list[User]:
        return [deepcopy(user) for user in self._by_id.values() if user.is_moderator]

    async def count_moderators(self) -> int:
        return sum(1 for user in self._by_id.values() if user.is_moderator)


class InMemoryWeightRepository(IWeightRepository):
    def __init__(self) -> None:
        self._entries: list[WeightEntry] = []

    async def upsert_for_local_day(
        self,
        entry: WeightEntry,
        *,
        day_start: datetime,
        day_end: datetime,
    ) -> WeightEntry:
        same_day = [
            item for item in self._entries if item.user_id == entry.user_id and day_start <= item.measured_at < day_end
        ]
        same_day.sort(key=lambda item: item.measured_at, reverse=True)
        if not same_day:
            stored = deepcopy(entry)
            self._entries.append(stored)
            return deepcopy(stored)
        primary = same_day[0]
        primary.rerecord(kilograms=entry.kilograms, measured_at=entry.measured_at, source=entry.source)
        keep_id = primary.id
        self._entries = [
            item
            for item in self._entries
            if not (item.user_id == entry.user_id and day_start <= item.measured_at < day_end and item.id != keep_id)
        ]
        return deepcopy(primary)

    async def latest_for_user(self, user_id: UUID) -> WeightEntry | None:
        items = [entry for entry in self._entries if entry.user_id == user_id]
        if not items:
            return None
        latest = max(items, key=lambda item: item.measured_at)
        return deepcopy(latest)

    async def history_for_user(self, user_id: UUID, *, limit: int = 50) -> list[WeightEntry]:
        items = sorted(
            (entry for entry in self._entries if entry.user_id == user_id),
            key=lambda item: item.measured_at,
            reverse=True,
        )
        return [deepcopy(item) for item in items[:limit]]


class InMemoryWeightReminderRepository(IWeightReminderRepository):
    def __init__(self) -> None:
        self._by_user: dict[UUID, WeightReminder] = {}

    async def get(self, user_id: UUID) -> WeightReminder | None:
        reminder = self._by_user.get(user_id)
        return deepcopy(reminder) if reminder else None

    async def save(self, reminder: WeightReminder) -> WeightReminder:
        stored = deepcopy(reminder)
        self._by_user[stored.user_id] = stored
        return deepcopy(stored)

    async def list_all(self) -> list[WeightReminder]:
        return [deepcopy(item) for item in self._by_user.values()]


class InMemoryProgressPhotoRepository(IProgressPhotoRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, ProgressPhotoSet] = {}

    async def get_set(self, set_id: UUID) -> ProgressPhotoSet | None:
        photo_set = self._by_id.get(set_id)
        return deepcopy(photo_set) if photo_set else None

    async def get_incomplete_for_user(self, user_id: UUID) -> ProgressPhotoSet | None:
        incomplete = [item for item in self._by_id.values() if item.user_id == user_id and not item.complete]
        if not incomplete:
            return None
        incomplete.sort(key=lambda item: item.local_date, reverse=True)
        return deepcopy(incomplete[0])

    async def get_for_user_local_date(self, user_id: UUID, local_date: date) -> ProgressPhotoSet | None:
        for item in self._by_id.values():
            if item.user_id == user_id and item.local_date == local_date:
                return deepcopy(item)
        return None

    async def save_set(self, photo_set: ProgressPhotoSet) -> ProgressPhotoSet:
        stored = deepcopy(photo_set)
        self._by_id[stored.id] = stored
        return deepcopy(stored)

    async def list_complete_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 30,
        offset: int = 0,
    ) -> list[ProgressPhotoSet]:
        items = sorted(
            (item for item in self._by_id.values() if item.user_id == user_id and item.complete),
            key=lambda item: item.local_date,
            reverse=True,
        )
        return [deepcopy(item) for item in items[offset : offset + limit]]


class InMemoryProgressPhotoReminderRepository(IProgressPhotoReminderRepository):
    def __init__(self) -> None:
        self._by_user: dict[UUID, ProgressPhotoReminder] = {}

    async def get(self, user_id: UUID) -> ProgressPhotoReminder | None:
        reminder = self._by_user.get(user_id)
        return deepcopy(reminder) if reminder else None

    async def save(self, reminder: ProgressPhotoReminder) -> ProgressPhotoReminder:
        stored = deepcopy(reminder)
        self._by_user[stored.user_id] = stored
        return deepcopy(stored)

    async def list_all(self) -> list[ProgressPhotoReminder]:
        return [deepcopy(item) for item in self._by_user.values()]


class InMemoryMeasurementRepository(IMeasurementRepository):
    def __init__(self) -> None:
        self._sites: dict[UUID, MeasurementSite] = {}
        self._guides: dict[UUID, MeasurementGuide] = {}
        self._entries: list[MeasurementEntry] = []

    async def get_site_by_id(self, site_id: UUID) -> MeasurementSite | None:
        site = self._sites.get(site_id)
        return deepcopy(site) if site else None

    async def get_fixed_site_by_code(self, code: str) -> MeasurementSite | None:
        for site in self._sites.values():
            if not site.is_custom and site.code == code:
                return deepcopy(site)
        return None

    async def list_sites_for_user(self, user_id: UUID) -> list[MeasurementSite]:
        sites = [site for site in self._sites.values() if not site.is_custom or site.user_id == user_id]
        return [deepcopy(site) for site in sorted(sites, key=lambda item: (item.is_custom, item.name))]

    async def add_site(self, site: MeasurementSite) -> MeasurementSite:
        stored = deepcopy(site)
        self._sites[stored.id] = stored
        return deepcopy(stored)

    async def get_custom_site_by_name(self, user_id: UUID, name: str) -> MeasurementSite | None:
        needle = name.strip().casefold()
        for site in self._sites.values():
            if site.is_custom and site.user_id == user_id and site.name.casefold() == needle:
                return deepcopy(site)
        return None

    async def get_guide(self, site_id: UUID) -> MeasurementGuide | None:
        guide = self._guides.get(site_id)
        return deepcopy(guide) if guide else None

    async def upsert_guide(self, guide: MeasurementGuide) -> MeasurementGuide:
        stored = deepcopy(guide)
        self._guides[stored.site_id] = stored
        return deepcopy(stored)

    async def add_entry(self, entry: MeasurementEntry) -> MeasurementEntry:
        stored = deepcopy(entry)
        self._entries.append(stored)
        return deepcopy(stored)

    async def history_for_user(
        self,
        user_id: UUID,
        *,
        site_id: UUID | None = None,
        limit: int = 50,
    ) -> list[MeasurementEntry]:
        items = [
            entry
            for entry in self._entries
            if entry.user_id == user_id and (site_id is None or entry.site_id == site_id)
        ]
        items.sort(key=lambda item: item.measured_at, reverse=True)
        return [deepcopy(item) for item in items[:limit]]


class InMemoryNutritionRepository(INutritionRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, NutritionRecommendation] = {}

    async def get_current(
        self,
        user_id: UUID,
        *,
        program_id: UUID,
        goal: Goal,
    ) -> NutritionRecommendation | None:
        items = [
            item
            for item in self._by_id.values()
            if item.user_id == user_id and item.program_id == program_id and item.goal == goal and not item.stale
        ]
        if not items:
            return None
        latest = max(items, key=lambda item: item.created_at)
        return deepcopy(latest)

    async def latest_for_user(self, user_id: UUID) -> NutritionRecommendation | None:
        items = [item for item in self._by_id.values() if item.user_id == user_id]
        if not items:
            return None
        latest = max(items, key=lambda item: item.created_at)
        return deepcopy(latest)

    async def mark_all_stale_for_user(self, user_id: UUID) -> None:
        for item in self._by_id.values():
            if item.user_id == user_id:
                item.stale = True

    async def add(self, recommendation: NutritionRecommendation) -> NutritionRecommendation:
        stored = deepcopy(recommendation)
        self._by_id[stored.id] = stored
        return deepcopy(stored)

    async def save(self, recommendation: NutritionRecommendation) -> NutritionRecommendation:
        if recommendation.id not in self._by_id:
            raise KeyError(recommendation.id)
        stored = deepcopy(recommendation)
        self._by_id[stored.id] = stored
        return deepcopy(stored)


class InMemoryWellbeingRepository(IWellbeingRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, WellbeingEntry] = {}

    async def add(self, entry: WellbeingEntry) -> WellbeingEntry:
        stored = deepcopy(entry)
        self._by_id[stored.id] = stored
        return deepcopy(stored)

    async def list_recent(self, user_id: UUID, *, limit: int = 20) -> list[WellbeingEntry]:
        items = [item for item in self._by_id.values() if item.user_id == user_id]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return [deepcopy(item) for item in items[:limit]]

    async def list_unapplied(self, user_id: UUID, *, limit: int = 20) -> list[WellbeingEntry]:
        items = [item for item in self._by_id.values() if item.user_id == user_id and item.applied_at is None]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return [deepcopy(item) for item in items[:limit]]

    async def mark_applied(self, entry_ids: list[UUID], *, applied_at: datetime | None = None) -> None:
        moment = applied_at or datetime.now(UTC)
        for entry_id in entry_ids:
            entry = self._by_id.get(entry_id)
            if entry is None:
                continue
            entry.applied_at = moment


class InMemoryTechniqueVideosRepository(ITechniqueVideosRepository):
    def __init__(self) -> None:
        self._by_slot: dict[UUID, TechniqueVideo] = {}

    async def get_by_slot_id(self, slot_id: UUID) -> TechniqueVideo | None:
        video = self._by_slot.get(slot_id)
        return deepcopy(video) if video else None

    async def list_for_session(self, session_id: UUID) -> list[TechniqueVideo]:
        return [deepcopy(video) for video in self._by_slot.values() if video.session_id == session_id]

    async def delete_for_session(self, session_id: UUID) -> None:
        stale = [slot_id for slot_id, video in self._by_slot.items() if video.session_id == session_id]
        for slot_id in stale:
            del self._by_slot[slot_id]

    async def upsert(self, video: TechniqueVideo) -> TechniqueVideo:
        stored = deepcopy(video)
        self._by_slot[stored.slot_id] = stored
        return deepcopy(stored)


class InMemoryUowRepositories(IUowRepositories):
    def __init__(
        self,
        users: InMemoryUsersRepository | None = None,
        weights: InMemoryWeightRepository | None = None,
        weight_reminders: InMemoryWeightReminderRepository | None = None,
        progress_photos: InMemoryProgressPhotoRepository | None = None,
        progress_photo_reminders: InMemoryProgressPhotoReminderRepository | None = None,
        measurements: InMemoryMeasurementRepository | None = None,
        programs: InMemoryProgramsRepository | None = None,
        proposals: InMemoryProposalsRepository | None = None,
        sessions: InMemorySessionsRepository | None = None,
        technique_videos: InMemoryTechniqueVideosRepository | None = None,
        nutrition: InMemoryNutritionRepository | None = None,
        wellbeing: InMemoryWellbeingRepository | None = None,
        coaches: InMemoryCoachesRepository | None = None,
        feedback: InMemoryFeedbackRepository | None = None,
    ) -> None:
        self._users = users or InMemoryUsersRepository()
        self._weights = weights or InMemoryWeightRepository()
        self._weight_reminders = weight_reminders or InMemoryWeightReminderRepository()
        self._progress_photos = progress_photos or InMemoryProgressPhotoRepository()
        self._progress_photo_reminders = progress_photo_reminders or InMemoryProgressPhotoReminderRepository()
        self._measurements = measurements or InMemoryMeasurementRepository()
        self._programs = programs or InMemoryProgramsRepository()
        self._proposals = proposals or InMemoryProposalsRepository(programs=self._programs)
        self._sessions = sessions or InMemorySessionsRepository()
        self._technique_videos = technique_videos or InMemoryTechniqueVideosRepository()
        self._nutrition = nutrition or InMemoryNutritionRepository()
        self._wellbeing = wellbeing or InMemoryWellbeingRepository()
        self._coaches = coaches or InMemoryCoachesRepository()
        self._feedback = feedback or InMemoryFeedbackRepository()

    @property
    def users(self) -> InMemoryUsersRepository:
        return self._users

    @property
    def weights(self) -> InMemoryWeightRepository:
        return self._weights

    @property
    def weight_reminders(self) -> InMemoryWeightReminderRepository:
        return self._weight_reminders

    @property
    def progress_photos(self) -> InMemoryProgressPhotoRepository:
        return self._progress_photos

    @property
    def progress_photo_reminders(self) -> InMemoryProgressPhotoReminderRepository:
        return self._progress_photo_reminders

    @property
    def measurements(self) -> InMemoryMeasurementRepository:
        return self._measurements

    @property
    def programs(self) -> IProgramsRepository:
        return self._programs

    @property
    def proposals(self) -> IProposalsRepository:
        return self._proposals

    @property
    def sessions(self) -> ISessionsRepository:
        return self._sessions

    @property
    def technique_videos(self) -> ITechniqueVideosRepository:
        return self._technique_videos

    @property
    def nutrition(self) -> INutritionRepository:
        return self._nutrition

    @property
    def wellbeing(self) -> IWellbeingRepository:
        return self._wellbeing

    @property
    def coaches(self) -> ICoachesRepository:
        return self._coaches

    @property
    def feedback(self) -> IFeedbackRepository:
        return self._feedback


class InMemoryUow(IUow):
    def __init__(self, repositories: InMemoryUowRepositories | None = None) -> None:
        self._repositories = repositories or InMemoryUowRepositories()

    @contextlib.asynccontextmanager
    async def _transaction(self) -> AsyncIterator[IUowRepositories]:
        yield self._repositories

    async def _commit(self) -> None:
        return None

    async def _rollback(self) -> None:
        return None


# Keep datetime import used by type checkers reading this module in isolation.
_ = datetime
