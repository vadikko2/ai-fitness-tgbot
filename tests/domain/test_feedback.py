from __future__ import annotations

from uuid import uuid4

import pytest

from fitness_bot.domain.enums import FeedbackKind, FeedbackStatus
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.feedback.ticket import FeedbackTicket, feedback_photo_object_key


def test_start_strips_text_and_stays_draft() -> None:
    ticket = FeedbackTicket.start(author_user_id=uuid4(), kind=FeedbackKind.IDEA, body="  больше фото прогресса  ")
    assert ticket.body == "больше фото прогресса"
    assert ticket.status == FeedbackStatus.DRAFT
    assert ticket.photos == []


def test_compose_session_accepts_photos_before_text() -> None:
    author_id = uuid4()
    ticket = FeedbackTicket.begin(author_user_id=author_id, kind=FeedbackKind.IDEA)
    ticket.attach_photo(
        object_key=feedback_photo_object_key(
            kind=FeedbackKind.IDEA,
            author_user_id=author_id,
            ticket_id=ticket.id,
            index=1,
            content_type="image/jpeg",
        ),
        content_type="image/jpeg",
        file_id="voice-then-photo",
    )
    with pytest.raises(DomainError, match="text is required"):
        ticket.submit()
    ticket.set_body("  хочу голосовые  ")
    assert ticket.body == "хочу голосовые"
    ticket.submit()
    assert ticket.status == FeedbackStatus.NEW


def test_empty_text_rejected() -> None:
    with pytest.raises(DomainError, match="text is required"):
        FeedbackTicket.start(author_user_id=uuid4(), kind=FeedbackKind.PROBLEM, body="   ")


def test_at_most_three_photos_and_only_before_send() -> None:
    author_id = uuid4()
    ticket = FeedbackTicket.start(author_user_id=author_id, kind=FeedbackKind.IDEA, body="идея")
    for index, token in enumerate(("a", "b", "c"), start=1):
        ticket.attach_photo(
            object_key=feedback_photo_object_key(
                kind=FeedbackKind.IDEA,
                author_user_id=author_id,
                ticket_id=ticket.id,
                index=index,
                content_type="image/jpeg",
            ),
            content_type="image/jpeg",
            file_id=token,
        )
    with pytest.raises(DomainError, match="at most 3 photos"):
        ticket.attach_photo(
            object_key=f"ideas/{author_id}/{ticket.id}/4.jpg",
            content_type="image/jpeg",
            file_id="d",
        )
    assert ticket.photo_file_ids == ["a", "b", "c"]
    assert all(photo.object_key.startswith("ideas/") for photo in ticket.photos)
    ticket.submit()
    assert ticket.status == FeedbackStatus.NEW
    with pytest.raises(DomainError, match="only before sending"):
        ticket.attach_photo(
            object_key=f"ideas/{author_id}/{ticket.id}/5.jpg",
            content_type="image/jpeg",
            file_id="e",
        )


def test_problem_photos_use_a_separate_folder() -> None:
    author_id = uuid4()
    ticket = FeedbackTicket.start(author_user_id=author_id, kind=FeedbackKind.PROBLEM, body="падает")
    key = feedback_photo_object_key(
        kind=FeedbackKind.PROBLEM,
        author_user_id=author_id,
        ticket_id=ticket.id,
        index=1,
        content_type="image/png",
    )
    assert key.startswith("problems/")
    assert key.endswith(".png")
    ticket.attach_photo(object_key=key, content_type="image/png", file_id="shot")
    with pytest.raises(DomainError, match="photo folder"):
        ticket.attach_photo(
            object_key=f"ideas/{author_id}/{ticket.id}/2.jpg",
            content_type="image/jpeg",
            file_id="wrong",
        )


def test_cancel_requires_reply_and_closes_ticket() -> None:
    ticket = FeedbackTicket.start(author_user_id=uuid4(), kind=FeedbackKind.PROBLEM, body="падает")
    ticket.submit()
    moderator = uuid4()
    with pytest.raises(DomainError, match="cancel reply is required"):
        ticket.cancel(moderator_user_id=moderator, reply="  ")
    ticket.cancel(moderator_user_id=moderator, reply=" не воспроизводится ")
    assert ticket.status == FeedbackStatus.CANCELLED
    assert ticket.moderator_reply == "не воспроизводится"
    with pytest.raises(DomainError, match="status cannot change"):
        ticket.resolve(moderator_user_id=moderator)


def test_in_progress_then_resolved() -> None:
    ticket = FeedbackTicket.start(author_user_id=uuid4(), kind=FeedbackKind.IDEA, body="идея")
    ticket.submit()
    moderator = uuid4()
    ticket.take_in_progress(moderator_user_id=moderator)
    with pytest.raises(DomainError, match="already in this status"):
        ticket.take_in_progress(moderator_user_id=moderator)
    ticket.resolve(moderator_user_id=moderator)
    assert ticket.status == FeedbackStatus.RESOLVED
    assert ticket.resolved_by_user_id == moderator
