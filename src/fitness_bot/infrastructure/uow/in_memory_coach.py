from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from uuid import UUID

from fitness_bot.domain.coach.application import CoachApplication, CoachApplicationModeratorMessage
from fitness_bot.domain.coach.invite import CoachInvite
from fitness_bot.domain.coach.link import CoachClientLink
from fitness_bot.domain.coach.note import CoachNote
from fitness_bot.domain.coach.profile import CoachProfile
from fitness_bot.domain.coach.report import CoachReport
from fitness_bot.domain.coach.review import CoachReview
from fitness_bot.domain.enums import (
    CoachApplicationStatus,
    CoachLinkStatus,
    CoachNoteVisibility,
    CoachReportStatus,
    CoachVerificationStatus,
)
from fitness_bot.service.interfaces.uow import ICoachesRepository


class InMemoryCoachesRepository(ICoachesRepository):
    def __init__(self) -> None:
        self._profiles: dict[UUID, CoachProfile] = {}
        self._applications: dict[UUID, CoachApplication] = {}
        self._mod_messages: list[CoachApplicationModeratorMessage] = []
        self._invites: dict[UUID, CoachInvite] = {}
        self._links: dict[UUID, CoachClientLink] = {}
        self._reviews: dict[tuple[UUID, UUID], CoachReview] = {}
        self._reports: dict[UUID, CoachReport] = {}
        self._notes: dict[UUID, CoachNote] = {}

    async def get_profile(self, user_id: UUID) -> CoachProfile | None:
        profile = self._profiles.get(user_id)
        return deepcopy(profile) if profile else None

    async def save_profile(self, profile: CoachProfile) -> CoachProfile:
        self._profiles[profile.user_id] = deepcopy(profile)
        return deepcopy(profile)

    async def search_verified(
        self,
        *,
        q: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[CoachProfile]:
        items = [
            p for p in self._profiles.values() if p.status == CoachVerificationStatus.VERIFIED and p.accepting_clients
        ]
        if q:
            needle = q.strip().casefold()
            items = [p for p in items if needle in p.display_name.casefold() or needle in p.bio.casefold()]
        items.sort(
            key=lambda p: (
                -(float(p.rating_avg) if p.rating_avg is not None else -1.0),
                -p.rating_count,
                p.display_name,
            ),
        )
        return [deepcopy(p) for p in items[offset : offset + limit]]

    async def add_application(self, application: CoachApplication) -> CoachApplication:
        self._applications[application.id] = deepcopy(application)
        return deepcopy(application)

    async def get_application(self, application_id: UUID) -> CoachApplication | None:
        app = self._applications.get(application_id)
        return deepcopy(app) if app else None

    async def list_pending_applications(self, *, limit: int = 20, offset: int = 0) -> list[CoachApplication]:
        items = [a for a in self._applications.values() if a.status == CoachApplicationStatus.PENDING]
        items.sort(key=lambda a: a.created_at)
        return [deepcopy(a) for a in items[offset : offset + limit]]

    async def resolve_application_if_pending(self, application: CoachApplication) -> CoachApplication | None:
        current = self._applications.get(application.id)
        if current is None or current.status != CoachApplicationStatus.PENDING:
            return None
        self._applications[application.id] = deepcopy(application)
        return deepcopy(application)

    async def add_moderator_message(
        self,
        message: CoachApplicationModeratorMessage,
    ) -> CoachApplicationModeratorMessage:
        self._mod_messages.append(deepcopy(message))
        return deepcopy(message)

    async def list_moderator_messages(self, application_id: UUID) -> list[CoachApplicationModeratorMessage]:
        return [deepcopy(m) for m in self._mod_messages if m.application_id == application_id]

    async def get_active_invite(self, coach_user_id: UUID) -> CoachInvite | None:
        for invite in self._invites.values():
            if invite.coach_user_id == coach_user_id and invite.revoked_at is None:
                return deepcopy(invite)
        return None

    async def get_invite_by_code(self, code: str) -> CoachInvite | None:
        normalized = code.strip().upper()
        for invite in self._invites.values():
            if invite.code == normalized:
                return deepcopy(invite)
        return None

    async def save_invite(self, invite: CoachInvite) -> CoachInvite:
        self._invites[invite.id] = deepcopy(invite)
        return deepcopy(invite)

    async def get_active_link(
        self,
        *,
        coach_user_id: UUID | None = None,
        client_user_id: UUID | None = None,
    ) -> CoachClientLink | None:
        for link in self._links.values():
            if link.status != CoachLinkStatus.ACTIVE:
                continue
            if coach_user_id is not None and link.coach_user_id != coach_user_id:
                continue
            if client_user_id is not None and link.client_user_id != client_user_id:
                continue
            return deepcopy(link)
        return None

    async def get_link(self, link_id: UUID) -> CoachClientLink | None:
        link = self._links.get(link_id)
        return deepcopy(link) if link else None

    async def list_active_clients(self, coach_user_id: UUID) -> list[CoachClientLink]:
        items = [
            link
            for link in self._links.values()
            if link.coach_user_id == coach_user_id and link.status == CoachLinkStatus.ACTIVE
        ]
        return [deepcopy(item) for item in items]

    async def count_active_clients(self, coach_user_id: UUID) -> int:
        return sum(
            1
            for link in self._links.values()
            if link.coach_user_id == coach_user_id and link.status == CoachLinkStatus.ACTIVE
        )

    async def has_any_link(self, *, coach_user_id: UUID, client_user_id: UUID) -> bool:
        return any(
            link.coach_user_id == coach_user_id and link.client_user_id == client_user_id
            for link in self._links.values()
        )

    async def save_link(self, link: CoachClientLink) -> CoachClientLink:
        self._links[link.id] = deepcopy(link)
        return deepcopy(link)

    async def upsert_review(self, review: CoachReview) -> CoachReview:
        key = (review.coach_user_id, review.author_user_id)
        existing = self._reviews.get(key)
        if existing is not None:
            review = review.model_copy(update={"id": existing.id, "created_at": existing.created_at})
        self._reviews[key] = deepcopy(review)
        return deepcopy(review)

    async def list_reviews(self, coach_user_id: UUID, *, limit: int = 20, offset: int = 0) -> list[CoachReview]:
        items = [r for r in self._reviews.values() if r.coach_user_id == coach_user_id]
        items.sort(key=lambda r: r.updated_at, reverse=True)
        return [deepcopy(r) for r in items[offset : offset + limit]]

    async def get_review(self, *, coach_user_id: UUID, author_user_id: UUID) -> CoachReview | None:
        review = self._reviews.get((coach_user_id, author_user_id))
        return deepcopy(review) if review else None

    async def delete_review(self, *, coach_user_id: UUID, author_user_id: UUID) -> None:
        self._reviews.pop((coach_user_id, author_user_id), None)

    async def recompute_rating(self, coach_user_id: UUID) -> CoachProfile | None:
        profile = await self.get_profile(coach_user_id)
        if profile is None:
            return None
        reviews = [r for r in self._reviews.values() if r.coach_user_id == coach_user_id]
        count = len(reviews)
        avg = (Decimal(sum(r.stars for r in reviews)) / Decimal(count)).quantize(Decimal("0.01")) if count else None
        profile.apply_rating_aggregate(avg=avg, count=count)
        return await self.save_profile(profile)

    async def add_report(self, report: CoachReport) -> CoachReport:
        self._reports[report.id] = deepcopy(report)
        return deepcopy(report)

    async def get_report(self, report_id: UUID) -> CoachReport | None:
        report = self._reports.get(report_id)
        return deepcopy(report) if report else None

    async def get_open_report(self, *, reporter_user_id: UUID, coach_user_id: UUID) -> CoachReport | None:
        for report in self._reports.values():
            if (
                report.reporter_user_id == reporter_user_id
                and report.coach_user_id == coach_user_id
                and report.status == CoachReportStatus.OPEN
            ):
                return deepcopy(report)
        return None

    async def save_report(self, report: CoachReport) -> CoachReport:
        self._reports[report.id] = deepcopy(report)
        return deepcopy(report)

    async def add_note(self, note: CoachNote) -> CoachNote:
        self._notes[note.id] = deepcopy(note)
        return deepcopy(note)

    async def list_shared_notes_for_client(
        self,
        client_user_id: UUID,
        *,
        session_id: UUID | None = None,
        limit: int = 20,
    ) -> list[CoachNote]:
        items = [
            n
            for n in self._notes.values()
            if n.client_user_id == client_user_id
            and n.visibility == CoachNoteVisibility.SHARED
            and n.revoked_at is None
            and (session_id is None or n.session_id == session_id)
        ]
        items.sort(key=lambda n: n.created_at, reverse=True)
        return [deepcopy(n) for n in items[:limit]]

    async def list_private_notes_for_coach(
        self,
        *,
        coach_user_id: UUID,
        client_user_id: UUID,
        limit: int = 20,
    ) -> list[CoachNote]:
        items = [
            n
            for n in self._notes.values()
            if n.coach_user_id == coach_user_id
            and n.client_user_id == client_user_id
            and n.visibility == CoachNoteVisibility.PRIVATE
            and n.revoked_at is None
        ]
        items.sort(key=lambda n: n.created_at, reverse=True)
        return [deepcopy(n) for n in items[:limit]]
