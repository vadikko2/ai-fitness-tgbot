from __future__ import annotations

import abc
import contextlib
from collections.abc import AsyncIterator
from datetime import date, datetime, time
from uuid import UUID

from fitness_bot.domain.body.measurement import MeasurementEntry, MeasurementGuide, MeasurementSite
from fitness_bot.domain.body.nutrition import NutritionRecommendation
from fitness_bot.domain.body.progress_photo import ProgressPhotoSet
from fitness_bot.domain.body.reminder import ProgressPhotoReminder, WeightReminder
from fitness_bot.domain.body.weight import WeightEntry
from fitness_bot.domain.body.wellbeing import WellbeingEntry
from fitness_bot.domain.coach.application import CoachApplication, CoachApplicationModeratorMessage
from fitness_bot.domain.coach.invite import CoachInvite
from fitness_bot.domain.coach.link import CoachClientLink
from fitness_bot.domain.coach.note import CoachNote
from fitness_bot.domain.coach.profile import CoachProfile
from fitness_bot.domain.coach.report import CoachReport
from fitness_bot.domain.coach.review import CoachReview
from fitness_bot.domain.enums import FeedbackKind, Goal
from fitness_bot.domain.feedback.ticket import FeedbackModeratorMessage, FeedbackTicket
from fitness_bot.domain.users.user import User
from fitness_bot.domain.workout.program import Program
from fitness_bot.domain.workout.proposal import Proposal
from fitness_bot.domain.workout.session import Session
from fitness_bot.domain.workout.technique_video import TechniqueVideo
from fitness_bot.domain.workout.training_reminder import TrainingReminderPrefs


class IUsersRepository(abc.ABC):
    @abc.abstractmethod
    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def add(self, user: User) -> User:
        raise NotImplementedError

    @abc.abstractmethod
    async def ensure(self, *, telegram_user_id: int, chat_id: int) -> tuple[User, bool]:
        """Get-or-create by telegram_user_id. Returns (user, created)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def save(self, user: User) -> User:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_with_timezone(self) -> list[User]:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_moderators(self) -> list[User]:
        raise NotImplementedError

    @abc.abstractmethod
    async def count_moderators(self) -> int:
        raise NotImplementedError


class IWeightRepository(abc.ABC):
    @abc.abstractmethod
    async def upsert_for_local_day(
        self,
        entry: WeightEntry,
        *,
        day_start: datetime,
        day_end: datetime,
    ) -> WeightEntry:
        """Keep a single weight row per user for ``[day_start, day_end)`` (UTC)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def latest_for_user(self, user_id: UUID) -> WeightEntry | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def history_for_user(self, user_id: UUID, *, limit: int = 50) -> list[WeightEntry]:
        raise NotImplementedError


class IWeightReminderRepository(abc.ABC):
    @abc.abstractmethod
    async def get(self, user_id: UUID) -> WeightReminder | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def save(self, reminder: WeightReminder) -> WeightReminder:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_all(self) -> list[WeightReminder]:
        raise NotImplementedError


class IProgressPhotoRepository(abc.ABC):
    @abc.abstractmethod
    async def get_set(self, set_id: UUID) -> ProgressPhotoSet | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_incomplete_for_user(self, user_id: UUID) -> ProgressPhotoSet | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_for_user_local_date(self, user_id: UUID, local_date: date) -> ProgressPhotoSet | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def save_set(self, photo_set: ProgressPhotoSet) -> ProgressPhotoSet:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_complete_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 30,
        offset: int = 0,
    ) -> list[ProgressPhotoSet]:
        raise NotImplementedError


class ITrainingReminderRepository(abc.ABC):
    @abc.abstractmethod
    async def get(self, user_id: UUID) -> TrainingReminderPrefs | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def save(self, prefs: TrainingReminderPrefs) -> TrainingReminderPrefs:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_all(self) -> list[TrainingReminderPrefs]:
        raise NotImplementedError


class IProgressPhotoReminderRepository(abc.ABC):
    @abc.abstractmethod
    async def get(self, user_id: UUID) -> ProgressPhotoReminder | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def save(self, reminder: ProgressPhotoReminder) -> ProgressPhotoReminder:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_all(self) -> list[ProgressPhotoReminder]:
        raise NotImplementedError


class IMeasurementRepository(abc.ABC):
    @abc.abstractmethod
    async def get_site_by_id(self, site_id: UUID) -> MeasurementSite | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_fixed_site_by_code(self, code: str) -> MeasurementSite | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_sites_for_user(self, user_id: UUID) -> list[MeasurementSite]:
        raise NotImplementedError

    @abc.abstractmethod
    async def add_site(self, site: MeasurementSite) -> MeasurementSite:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_custom_site_by_name(self, user_id: UUID, name: str) -> MeasurementSite | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_guide(self, site_id: UUID) -> MeasurementGuide | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def upsert_guide(self, guide: MeasurementGuide) -> MeasurementGuide:
        raise NotImplementedError

    @abc.abstractmethod
    async def add_entry(self, entry: MeasurementEntry) -> MeasurementEntry:
        raise NotImplementedError

    @abc.abstractmethod
    async def history_for_user(
        self,
        user_id: UUID,
        *,
        site_id: UUID | None = None,
        limit: int = 50,
    ) -> list[MeasurementEntry]:
        raise NotImplementedError


class IProgramsRepository(abc.ABC):
    @abc.abstractmethod
    async def get_by_id(self, program_id: UUID) -> Program | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_active_for_user(self, user_id: UUID) -> Program | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def add(self, program: Program) -> Program:
        raise NotImplementedError

    @abc.abstractmethod
    async def save(self, program: Program) -> Program:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_catalog_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Program]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_by_distribution_code(self, code: str) -> Program | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def find_existing_claim(self, *, user_id: UUID, source_program_id: UUID) -> Program | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def publish(self, program: Program) -> Program:
        raise NotImplementedError

    @abc.abstractmethod
    async def unpublish(self, program: Program) -> Program:
        raise NotImplementedError


class ICoachesRepository(abc.ABC):
    @abc.abstractmethod
    async def get_profile(self, user_id: UUID) -> CoachProfile | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def save_profile(self, profile: CoachProfile) -> CoachProfile:
        raise NotImplementedError

    @abc.abstractmethod
    async def search_verified(
        self,
        *,
        q: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[CoachProfile]:
        raise NotImplementedError

    @abc.abstractmethod
    async def add_application(self, application: CoachApplication) -> CoachApplication:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_application(self, application_id: UUID) -> CoachApplication | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_pending_applications(self, *, limit: int = 20, offset: int = 0) -> list[CoachApplication]:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_applications_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CoachApplication]:
        raise NotImplementedError

    @abc.abstractmethod
    async def resolve_application_if_pending(
        self,
        application: CoachApplication,
    ) -> CoachApplication | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def add_moderator_message(
        self,
        message: CoachApplicationModeratorMessage,
    ) -> CoachApplicationModeratorMessage:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_moderator_messages(self, application_id: UUID) -> list[CoachApplicationModeratorMessage]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_active_invite(self, coach_user_id: UUID) -> CoachInvite | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_invite_by_code(self, code: str) -> CoachInvite | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def save_invite(self, invite: CoachInvite) -> CoachInvite:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_active_link(
        self,
        *,
        coach_user_id: UUID | None = None,
        client_user_id: UUID | None = None,
    ) -> CoachClientLink | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_link(self, link_id: UUID) -> CoachClientLink | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_active_clients(self, coach_user_id: UUID) -> list[CoachClientLink]:
        raise NotImplementedError

    @abc.abstractmethod
    async def count_active_clients(self, coach_user_id: UUID) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    async def has_any_link(self, *, coach_user_id: UUID, client_user_id: UUID) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    async def save_link(self, link: CoachClientLink) -> CoachClientLink:
        raise NotImplementedError

    @abc.abstractmethod
    async def upsert_review(self, review: CoachReview) -> CoachReview:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_reviews(self, coach_user_id: UUID, *, limit: int = 20, offset: int = 0) -> list[CoachReview]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_review(self, *, coach_user_id: UUID, author_user_id: UUID) -> CoachReview | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def delete_review(self, *, coach_user_id: UUID, author_user_id: UUID) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def recompute_rating(self, coach_user_id: UUID) -> CoachProfile | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def add_report(self, report: CoachReport) -> CoachReport:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_report(self, report_id: UUID) -> CoachReport | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_open_report(self, *, reporter_user_id: UUID, coach_user_id: UUID) -> CoachReport | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def save_report(self, report: CoachReport) -> CoachReport:
        raise NotImplementedError

    @abc.abstractmethod
    async def add_note(self, note: CoachNote) -> CoachNote:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_shared_notes_for_client(
        self,
        client_user_id: UUID,
        *,
        session_id: UUID | None = None,
        limit: int = 20,
    ) -> list[CoachNote]:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_private_notes_for_coach(
        self,
        *,
        coach_user_id: UUID,
        client_user_id: UUID,
        limit: int = 20,
    ) -> list[CoachNote]:
        raise NotImplementedError


class IFeedbackRepository(abc.ABC):
    @abc.abstractmethod
    async def add(self, ticket: FeedbackTicket) -> FeedbackTicket:
        raise NotImplementedError

    @abc.abstractmethod
    async def get(self, ticket_id: UUID) -> FeedbackTicket | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def save(self, ticket: FeedbackTicket) -> FeedbackTicket:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_for_author(
        self,
        author_user_id: UUID,
        kind: FeedbackKind,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[FeedbackTicket], int]:
        """Submitted tickets newest first, plus the total count."""
        raise NotImplementedError

    @abc.abstractmethod
    async def add_moderator_message(self, message: FeedbackModeratorMessage) -> FeedbackModeratorMessage:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_moderator_messages(self, ticket_id: UUID) -> list[FeedbackModeratorMessage]:
        raise NotImplementedError


class IProposalsRepository(abc.ABC):
    @abc.abstractmethod
    async def get_by_id(self, proposal_id: UUID) -> Proposal | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_pending_for_user(self, user_id: UUID) -> Proposal | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def save(self, proposal: Proposal) -> Proposal:
        raise NotImplementedError

    @abc.abstractmethod
    async def attach_days_to_program(self, proposal_id: UUID, program_id: UUID) -> None:
        """Move workout_days from proposal to program (clear proposal_id, set program_id)."""
        raise NotImplementedError


class ISessionsRepository(abc.ABC):
    @abc.abstractmethod
    async def get_by_id(self, session_id: UUID) -> Session | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_open_for_user(self, user_id: UUID) -> Session | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_completed_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Session]:
        raise NotImplementedError

    @abc.abstractmethod
    async def add(self, session: Session) -> Session:
        raise NotImplementedError

    @abc.abstractmethod
    async def save(self, session: Session) -> Session:
        raise NotImplementedError

    @abc.abstractmethod
    async def delete(self, session_id: UUID) -> None:
        raise NotImplementedError


class ITechniqueVideosRepository(abc.ABC):
    @abc.abstractmethod
    async def get_by_slot_id(self, slot_id: UUID) -> TechniqueVideo | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_for_session(self, session_id: UUID) -> list[TechniqueVideo]:
        raise NotImplementedError

    @abc.abstractmethod
    async def delete_for_session(self, session_id: UUID) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def upsert(self, video: TechniqueVideo) -> TechniqueVideo:
        raise NotImplementedError


class INutritionRepository(abc.ABC):
    @abc.abstractmethod
    async def get_current(
        self,
        user_id: UUID,
        *,
        program_id: UUID,
        goal: Goal,
    ) -> NutritionRecommendation | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def latest_for_user(self, user_id: UUID) -> NutritionRecommendation | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def mark_all_stale_for_user(self, user_id: UUID) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def add(self, recommendation: NutritionRecommendation) -> NutritionRecommendation:
        raise NotImplementedError

    @abc.abstractmethod
    async def save(self, recommendation: NutritionRecommendation) -> NutritionRecommendation:
        raise NotImplementedError


class IWellbeingRepository(abc.ABC):
    @abc.abstractmethod
    async def add(self, entry: WellbeingEntry) -> WellbeingEntry:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_recent(self, user_id: UUID, *, limit: int = 20) -> list[WellbeingEntry]:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_unapplied(self, user_id: UUID, *, limit: int = 20) -> list[WellbeingEntry]:
        raise NotImplementedError

    @abc.abstractmethod
    async def mark_applied(self, entry_ids: list[UUID], *, applied_at: datetime | None = None) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_page(self, user_id: UUID, *, offset: int = 0, limit: int = 10) -> list[WellbeingEntry]:
        raise NotImplementedError

    @abc.abstractmethod
    async def link_to_proposal(self, entry_ids: list[UUID], proposal_id: UUID) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def mark_applied_for_proposal(
        self,
        proposal_id: UUID,
        *,
        applied_at: datetime | None = None,
    ) -> list[UUID]:
        raise NotImplementedError


class IUowRepositories(abc.ABC):
    @property
    @abc.abstractmethod
    def users(self) -> IUsersRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def weights(self) -> IWeightRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def weight_reminders(self) -> IWeightReminderRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def training_reminders(self) -> ITrainingReminderRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def progress_photos(self) -> IProgressPhotoRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def progress_photo_reminders(self) -> IProgressPhotoReminderRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def measurements(self) -> IMeasurementRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def programs(self) -> IProgramsRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def proposals(self) -> IProposalsRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def sessions(self) -> ISessionsRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def technique_videos(self) -> ITechniqueVideosRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def nutrition(self) -> INutritionRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def wellbeing(self) -> IWellbeingRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def coaches(self) -> ICoachesRepository:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def feedback(self) -> IFeedbackRepository:
        raise NotImplementedError


class IUow(abc.ABC):
    @contextlib.asynccontextmanager
    async def transaction(self) -> AsyncIterator[IUowRepositories]:
        try:
            async with self._transaction() as repos:
                yield repos
            await self._commit()
        finally:
            await self._rollback()

    @abc.abstractmethod
    @contextlib.asynccontextmanager
    def _transaction(self) -> AsyncIterator[IUowRepositories]:
        raise NotImplementedError

    @abc.abstractmethod
    async def _commit(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def _rollback(self) -> None:
        raise NotImplementedError


# Re-export common types used by repository signatures for convenience.
__all__ = [
    "ICoachesRepository",
    "IFeedbackRepository",
    "IMeasurementRepository",
    "INutritionRepository",
    "IProgramsRepository",
    "IProgressPhotoReminderRepository",
    "IProgressPhotoRepository",
    "IProposalsRepository",
    "ISessionsRepository",
    "ITechniqueVideosRepository",
    "ITrainingReminderRepository",
    "IUow",
    "IUowRepositories",
    "IUsersRepository",
    "IWeightReminderRepository",
    "IWeightRepository",
    "IWellbeingRepository",
    "MeasurementEntry",
    "MeasurementGuide",
    "MeasurementSite",
    "NutritionRecommendation",
    "Program",
    "ProgressPhotoReminder",
    "ProgressPhotoSet",
    "Proposal",
    "Session",
    "TechniqueVideo",
    "TrainingReminderPrefs",
    "User",
    "WeightEntry",
    "WeightReminder",
    "WellbeingEntry",
    "UUID",
    "date",
    "datetime",
    "time",
]
