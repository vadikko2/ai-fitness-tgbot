from __future__ import annotations

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
from fitness_bot.infrastructure.db.models import (
    CoachApplicationModeratorMessageRow,
    CoachApplicationRow,
    CoachClientLinkRow,
    CoachInviteRow,
    CoachNoteRow,
    CoachProfileRow,
    CoachReportRow,
    CoachReviewRow,
)


def coach_profile_to_domain(row: CoachProfileRow) -> CoachProfile:
    return CoachProfile(
        user_id=row.user_id,
        display_name=row.display_name,
        bio=row.bio or "",
        portfolio_url=row.portfolio_url,
        status=CoachVerificationStatus(row.status),
        accepting_clients=row.accepting_clients,
        rating_avg=row.rating_avg,
        rating_count=row.rating_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def apply_coach_profile_to_row(row: CoachProfileRow, profile: CoachProfile) -> None:
    row.display_name = profile.display_name
    row.bio = profile.bio
    row.portfolio_url = profile.portfolio_url
    row.status = profile.status.value
    row.accepting_clients = profile.accepting_clients
    row.rating_avg = profile.rating_avg
    row.rating_count = profile.rating_count
    row.updated_at = profile.updated_at


def coach_application_to_domain(row: CoachApplicationRow) -> CoachApplication:
    return CoachApplication(
        id=row.id,
        user_id=row.user_id,
        display_name=row.display_name,
        bio=row.bio,
        portfolio_url=row.portfolio_url,
        credential_object_key=row.credential_object_key,
        credential_content_type=row.credential_content_type,
        credential_byte_size=row.credential_byte_size,
        credential_caption=row.credential_caption,
        status=CoachApplicationStatus(row.status),
        moderator_comment=row.moderator_comment,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
        resolved_by_user_id=row.resolved_by_user_id,
    )


def coach_moderator_message_to_domain(row: CoachApplicationModeratorMessageRow) -> CoachApplicationModeratorMessage:
    return CoachApplicationModeratorMessage(
        id=row.id,
        application_id=row.application_id,
        moderator_user_id=row.moderator_user_id,
        chat_id=row.chat_id,
        message_id=row.message_id,
        media_message_id=row.media_message_id,
        created_at=row.created_at,
    )


def coach_invite_to_domain(row: CoachInviteRow) -> CoachInvite:
    return CoachInvite(
        id=row.id,
        code=row.code,
        coach_user_id=row.coach_user_id,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        uses_count=row.uses_count,
        max_uses=row.max_uses,
        expires_at=row.expires_at,
    )


def apply_coach_invite_to_row(row: CoachInviteRow, invite: CoachInvite) -> None:
    row.code = invite.code
    row.coach_user_id = invite.coach_user_id
    row.revoked_at = invite.revoked_at
    row.uses_count = invite.uses_count
    row.max_uses = invite.max_uses
    row.expires_at = invite.expires_at


def coach_link_to_domain(row: CoachClientLinkRow) -> CoachClientLink:
    return CoachClientLink(
        id=row.id,
        coach_user_id=row.coach_user_id,
        client_user_id=row.client_user_id,
        status=CoachLinkStatus(row.status),
        created_at=row.created_at,
        activated_at=row.activated_at,
        revoked_at=row.revoked_at,
        revoked_by_user_id=row.revoked_by_user_id,
    )


def apply_coach_link_to_row(row: CoachClientLinkRow, link: CoachClientLink) -> None:
    row.status = link.status.value
    row.activated_at = link.activated_at
    row.revoked_at = link.revoked_at
    row.revoked_by_user_id = link.revoked_by_user_id


def coach_review_to_domain(row: CoachReviewRow) -> CoachReview:
    return CoachReview(
        id=row.id,
        coach_user_id=row.coach_user_id,
        author_user_id=row.author_user_id,
        stars=row.stars,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def coach_report_to_domain(row: CoachReportRow) -> CoachReport:
    return CoachReport(
        id=row.id,
        reporter_user_id=row.reporter_user_id,
        coach_user_id=row.coach_user_id,
        body=row.body,
        status=CoachReportStatus(row.status),
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


def coach_note_to_domain(row: CoachNoteRow) -> CoachNote:
    return CoachNote(
        id=row.id,
        coach_user_id=row.coach_user_id,
        client_user_id=row.client_user_id,
        visibility=CoachNoteVisibility(row.visibility),
        body=row.body,
        session_id=row.session_id,
        slot_id=row.slot_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        revoked_at=row.revoked_at,
    )
