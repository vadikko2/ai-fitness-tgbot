from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
from fitness_bot.infrastructure.db.mappers_coach import (
    apply_coach_invite_to_row,
    apply_coach_link_to_row,
    apply_coach_profile_to_row,
    coach_application_to_domain,
    coach_invite_to_domain,
    coach_link_to_domain,
    coach_moderator_message_to_domain,
    coach_note_to_domain,
    coach_profile_to_domain,
    coach_report_to_domain,
    coach_review_to_domain,
)
from fitness_bot.infrastructure.db.models import (
    CoachApplicationModeratorMessageRow,
    CoachApplicationRow,
    CoachClientLinkRow,
    CoachInviteRow,
    CoachNoteRow,
    CoachProfileRow,
    CoachReportRow,
    CoachReviewRow,
    UserRow,
)
from fitness_bot.service.interfaces.uow import ICoachesRepository


class SqlAlchemyCoachesRepository(ICoachesRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_profile(self, user_id: UUID) -> CoachProfile | None:
        row = await self._session.get(CoachProfileRow, user_id)
        return coach_profile_to_domain(row) if row else None

    async def save_profile(self, profile: CoachProfile) -> CoachProfile:
        row = await self._session.get(CoachProfileRow, profile.user_id)
        if row is None:
            row = CoachProfileRow(user_id=profile.user_id, display_name=profile.display_name)
            self._session.add(row)
        apply_coach_profile_to_row(row, profile)
        await self._session.flush()
        return coach_profile_to_domain(row)

    async def search_verified(
        self,
        *,
        q: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[CoachProfile]:
        stmt: Select[tuple[CoachProfileRow]] = select(CoachProfileRow).where(
            CoachProfileRow.status == CoachVerificationStatus.VERIFIED.value,
            CoachProfileRow.accepting_clients.is_(True),
        )
        if q:
            pattern = f"%{q.strip()}%"
            stmt = stmt.join(UserRow, UserRow.id == CoachProfileRow.user_id).where(
                or_(
                    CoachProfileRow.display_name.ilike(pattern),
                    CoachProfileRow.bio.ilike(pattern),
                    UserRow.telegram_username.ilike(pattern),
                    UserRow.display_name.ilike(pattern),
                ),
            )
        stmt = (
            stmt.order_by(
                CoachProfileRow.rating_avg.desc().nulls_last(),
                CoachProfileRow.rating_count.desc(),
                CoachProfileRow.display_name.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [coach_profile_to_domain(row) for row in rows]

    async def add_application(self, application: CoachApplication) -> CoachApplication:
        row = CoachApplicationRow(
            id=application.id,
            user_id=application.user_id,
            display_name=application.display_name,
            bio=application.bio,
            portfolio_url=application.portfolio_url,
            credential_object_key=application.credential_object_key,
            credential_content_type=application.credential_content_type,
            credential_byte_size=application.credential_byte_size,
            credential_caption=application.credential_caption,
            status=application.status.value,
            moderator_comment=application.moderator_comment,
            created_at=application.created_at,
            resolved_at=application.resolved_at,
            resolved_by_user_id=application.resolved_by_user_id,
        )
        self._session.add(row)
        await self._session.flush()
        return coach_application_to_domain(row)

    async def get_application(self, application_id: UUID) -> CoachApplication | None:
        row = await self._session.get(CoachApplicationRow, application_id)
        return coach_application_to_domain(row) if row else None

    async def list_pending_applications(self, *, limit: int = 20, offset: int = 0) -> list[CoachApplication]:
        stmt = (
            select(CoachApplicationRow)
            .where(CoachApplicationRow.status == CoachApplicationStatus.PENDING.value)
            .order_by(CoachApplicationRow.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [coach_application_to_domain(row) for row in rows]

    async def list_applications_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CoachApplication]:
        stmt = (
            select(CoachApplicationRow)
            .where(CoachApplicationRow.user_id == user_id)
            .order_by(CoachApplicationRow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [coach_application_to_domain(row) for row in rows]

    async def resolve_application_if_pending(
        self,
        application: CoachApplication,
    ) -> CoachApplication | None:
        """Optimistic lock: UPDATE … WHERE status=pending RETURNING."""
        stmt = (
            update(CoachApplicationRow)
            .where(
                CoachApplicationRow.id == application.id,
                CoachApplicationRow.status == CoachApplicationStatus.PENDING.value,
            )
            .values(
                status=application.status.value,
                resolved_at=application.resolved_at,
                resolved_by_user_id=application.resolved_by_user_id,
                moderator_comment=application.moderator_comment,
            )
            .returning(CoachApplicationRow.id)
        )
        updated_id = (await self._session.execute(stmt)).scalar_one_or_none()
        if updated_id is None:
            return None
        await self._session.flush()
        return await self.get_application(application.id)

    async def add_moderator_message(
        self,
        message: CoachApplicationModeratorMessage,
    ) -> CoachApplicationModeratorMessage:
        row = CoachApplicationModeratorMessageRow(
            id=message.id,
            application_id=message.application_id,
            moderator_user_id=message.moderator_user_id,
            chat_id=message.chat_id,
            message_id=message.message_id,
            media_message_id=message.media_message_id,
            created_at=message.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return coach_moderator_message_to_domain(row)

    async def list_moderator_messages(self, application_id: UUID) -> list[CoachApplicationModeratorMessage]:
        stmt = select(CoachApplicationModeratorMessageRow).where(
            CoachApplicationModeratorMessageRow.application_id == application_id,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [coach_moderator_message_to_domain(row) for row in rows]

    async def get_active_invite(self, coach_user_id: UUID) -> CoachInvite | None:
        stmt = select(CoachInviteRow).where(
            CoachInviteRow.coach_user_id == coach_user_id,
            CoachInviteRow.revoked_at.is_(None),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return coach_invite_to_domain(row) if row else None

    async def get_invite_by_code(self, code: str) -> CoachInvite | None:
        stmt = select(CoachInviteRow).where(CoachInviteRow.code == code.strip().upper())
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return coach_invite_to_domain(row) if row else None

    async def save_invite(self, invite: CoachInvite) -> CoachInvite:
        row = await self._session.get(CoachInviteRow, invite.id)
        if row is None:
            row = CoachInviteRow(id=invite.id, code=invite.code, coach_user_id=invite.coach_user_id)
            self._session.add(row)
        apply_coach_invite_to_row(row, invite)
        await self._session.flush()
        return coach_invite_to_domain(row)

    async def get_active_link(
        self,
        *,
        coach_user_id: UUID | None = None,
        client_user_id: UUID | None = None,
    ) -> CoachClientLink | None:
        clauses = [CoachClientLinkRow.status == CoachLinkStatus.ACTIVE.value]
        if coach_user_id is not None:
            clauses.append(CoachClientLinkRow.coach_user_id == coach_user_id)
        if client_user_id is not None:
            clauses.append(CoachClientLinkRow.client_user_id == client_user_id)
        stmt = select(CoachClientLinkRow).where(and_(*clauses))
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return coach_link_to_domain(row) if row else None

    async def get_link(self, link_id: UUID) -> CoachClientLink | None:
        row = await self._session.get(CoachClientLinkRow, link_id)
        return coach_link_to_domain(row) if row else None

    async def list_active_clients(self, coach_user_id: UUID) -> list[CoachClientLink]:
        stmt = (
            select(CoachClientLinkRow)
            .where(
                CoachClientLinkRow.coach_user_id == coach_user_id,
                CoachClientLinkRow.status == CoachLinkStatus.ACTIVE.value,
            )
            .order_by(CoachClientLinkRow.activated_at.desc().nulls_last())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [coach_link_to_domain(row) for row in rows]

    async def count_active_clients(self, coach_user_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(CoachClientLinkRow)
            .where(
                CoachClientLinkRow.coach_user_id == coach_user_id,
                CoachClientLinkRow.status == CoachLinkStatus.ACTIVE.value,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def has_any_link(self, *, coach_user_id: UUID, client_user_id: UUID) -> bool:
        stmt = select(CoachClientLinkRow.id).where(
            CoachClientLinkRow.coach_user_id == coach_user_id,
            CoachClientLinkRow.client_user_id == client_user_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def save_link(self, link: CoachClientLink) -> CoachClientLink:
        row = await self._session.get(CoachClientLinkRow, link.id)
        if row is None:
            row = CoachClientLinkRow(
                id=link.id,
                coach_user_id=link.coach_user_id,
                client_user_id=link.client_user_id,
                status=link.status.value,
                created_at=link.created_at,
                activated_at=link.activated_at,
            )
            self._session.add(row)
        else:
            apply_coach_link_to_row(row, link)
        await self._session.flush()
        return coach_link_to_domain(row)

    async def upsert_review(self, review: CoachReview) -> CoachReview:
        stmt = select(CoachReviewRow).where(
            CoachReviewRow.coach_user_id == review.coach_user_id,
            CoachReviewRow.author_user_id == review.author_user_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = CoachReviewRow(
                id=review.id,
                coach_user_id=review.coach_user_id,
                author_user_id=review.author_user_id,
                stars=review.stars,
                body=review.body,
                created_at=review.created_at,
                updated_at=review.updated_at,
            )
            self._session.add(row)
        else:
            row.stars = review.stars
            row.body = review.body
            row.updated_at = review.updated_at
        await self._session.flush()
        return coach_review_to_domain(row)

    async def list_reviews(self, coach_user_id: UUID, *, limit: int = 20, offset: int = 0) -> list[CoachReview]:
        stmt = (
            select(CoachReviewRow)
            .where(CoachReviewRow.coach_user_id == coach_user_id)
            .order_by(CoachReviewRow.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [coach_review_to_domain(row) for row in rows]

    async def get_review(self, *, coach_user_id: UUID, author_user_id: UUID) -> CoachReview | None:
        stmt = select(CoachReviewRow).where(
            CoachReviewRow.coach_user_id == coach_user_id,
            CoachReviewRow.author_user_id == author_user_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return coach_review_to_domain(row) if row else None

    async def delete_review(self, *, coach_user_id: UUID, author_user_id: UUID) -> None:
        stmt = select(CoachReviewRow).where(
            CoachReviewRow.coach_user_id == coach_user_id,
            CoachReviewRow.author_user_id == author_user_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    async def recompute_rating(self, coach_user_id: UUID) -> CoachProfile | None:
        profile = await self.get_profile(coach_user_id)
        if profile is None:
            return None
        stmt = select(func.avg(CoachReviewRow.stars), func.count(CoachReviewRow.id)).where(
            CoachReviewRow.coach_user_id == coach_user_id,
        )
        avg_val, count_val = (await self._session.execute(stmt)).one()
        count = int(count_val or 0)
        avg = Decimal(str(avg_val)).quantize(Decimal("0.01")) if count and avg_val is not None else None
        profile.apply_rating_aggregate(avg=avg, count=count)
        return await self.save_profile(profile)

    async def add_report(self, report: CoachReport) -> CoachReport:
        row = CoachReportRow(
            id=report.id,
            reporter_user_id=report.reporter_user_id,
            coach_user_id=report.coach_user_id,
            body=report.body,
            status=report.status.value,
            created_at=report.created_at,
            resolved_at=report.resolved_at,
        )
        self._session.add(row)
        await self._session.flush()
        return coach_report_to_domain(row)

    async def get_report(self, report_id: UUID) -> CoachReport | None:
        row = await self._session.get(CoachReportRow, report_id)
        return coach_report_to_domain(row) if row else None

    async def get_open_report(self, *, reporter_user_id: UUID, coach_user_id: UUID) -> CoachReport | None:
        stmt = select(CoachReportRow).where(
            CoachReportRow.reporter_user_id == reporter_user_id,
            CoachReportRow.coach_user_id == coach_user_id,
            CoachReportRow.status == CoachReportStatus.OPEN.value,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return coach_report_to_domain(row) if row else None

    async def save_report(self, report: CoachReport) -> CoachReport:
        row = await self._session.get(CoachReportRow, report.id)
        if row is None:
            return await self.add_report(report)
        row.status = report.status.value
        row.resolved_at = report.resolved_at
        await self._session.flush()
        return coach_report_to_domain(row)

    async def add_note(self, note: CoachNote) -> CoachNote:
        row = CoachNoteRow(
            id=note.id,
            coach_user_id=note.coach_user_id,
            client_user_id=note.client_user_id,
            visibility=note.visibility.value,
            body=note.body,
            session_id=note.session_id,
            slot_id=note.slot_id,
            created_at=note.created_at,
            updated_at=note.updated_at,
            revoked_at=note.revoked_at,
        )
        self._session.add(row)
        await self._session.flush()
        return coach_note_to_domain(row)

    async def list_shared_notes_for_client(
        self,
        client_user_id: UUID,
        *,
        session_id: UUID | None = None,
        limit: int = 20,
    ) -> list[CoachNote]:
        clauses = [
            CoachNoteRow.client_user_id == client_user_id,
            CoachNoteRow.visibility == CoachNoteVisibility.SHARED.value,
            CoachNoteRow.revoked_at.is_(None),
        ]
        if session_id is not None:
            clauses.append(CoachNoteRow.session_id == session_id)
        stmt = select(CoachNoteRow).where(and_(*clauses)).order_by(CoachNoteRow.created_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [coach_note_to_domain(row) for row in rows]

    async def list_private_notes_for_coach(
        self,
        *,
        coach_user_id: UUID,
        client_user_id: UUID,
        limit: int = 20,
    ) -> list[CoachNote]:
        stmt = (
            select(CoachNoteRow)
            .where(
                CoachNoteRow.coach_user_id == coach_user_id,
                CoachNoteRow.client_user_id == client_user_id,
                CoachNoteRow.visibility == CoachNoteVisibility.PRIVATE.value,
                CoachNoteRow.revoked_at.is_(None),
            )
            .order_by(CoachNoteRow.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [coach_note_to_domain(row) for row in rows]
