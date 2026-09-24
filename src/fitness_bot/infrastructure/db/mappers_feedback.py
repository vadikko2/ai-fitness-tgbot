from __future__ import annotations

import json

from fitness_bot.domain.enums import FeedbackKind, FeedbackStatus
from fitness_bot.domain.feedback.ticket import FeedbackModeratorMessage, FeedbackPhoto, FeedbackTicket
from fitness_bot.infrastructure.db.models import FeedbackModeratorMessageRow, FeedbackTicketRow


def feedback_ticket_to_domain(row: FeedbackTicketRow) -> FeedbackTicket:
    raw_photos = row.photo_file_ids or "[]"
    try:
        photos = json.loads(raw_photos)
    except json.JSONDecodeError:
        photos = []
    if not isinstance(photos, list):
        photos = []
    return FeedbackTicket(
        id=row.id,
        author_user_id=row.author_user_id,
        kind=FeedbackKind(row.kind),
        body=row.body,
        status=FeedbackStatus(row.status),
        moderator_reply=row.moderator_reply,
        resolved_by_user_id=row.resolved_by_user_id,
        photos=[_photo_from_stored(item) for item in photos],
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
    )


def apply_feedback_ticket_to_row(row: FeedbackTicketRow, ticket: FeedbackTicket) -> None:
    row.author_user_id = ticket.author_user_id
    row.kind = ticket.kind.value
    row.body = ticket.body
    row.status = ticket.status.value
    row.moderator_reply = ticket.moderator_reply
    row.resolved_by_user_id = ticket.resolved_by_user_id
    row.photo_file_ids = json.dumps([photo.model_dump() for photo in ticket.photos])
    row.created_at = ticket.created_at
    row.updated_at = ticket.updated_at
    row.resolved_at = ticket.resolved_at


def _photo_from_stored(item: object) -> FeedbackPhoto:
    if isinstance(item, str):
        return FeedbackPhoto(object_key="", content_type="image/jpeg", file_id=item)
    if isinstance(item, dict):
        return FeedbackPhoto(
            object_key=str(item.get("object_key") or ""),
            content_type=str(item.get("content_type") or "image/jpeg"),
            file_id=str(item.get("file_id") or ""),
        )
    return FeedbackPhoto(object_key="", content_type="image/jpeg", file_id="")


def feedback_message_to_domain(row: FeedbackModeratorMessageRow) -> FeedbackModeratorMessage:
    return FeedbackModeratorMessage(
        id=row.id,
        ticket_id=row.ticket_id,
        moderator_user_id=row.moderator_user_id,
        chat_id=row.chat_id,
        message_id=row.message_id,
        created_at=row.created_at,
    )
