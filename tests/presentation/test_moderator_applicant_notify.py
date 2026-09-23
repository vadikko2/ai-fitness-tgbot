from __future__ import annotations

from uuid import uuid4

from fitness_bot.presentation.keyboards import (
    coach_application_approved_keyboard,
    coach_application_rejected_keyboard,
)
from fitness_bot.presentation.routers.moderator import applicant_resolution_keyboard
from fitness_bot.service.models.commands.coach import (
    ApproveCoachApplicationCommandResult,
    RejectCoachApplicationCommandResult,
)


def test_applicant_resolution_keyboard_approved_opens_cabinet() -> None:
    result = ApproveCoachApplicationCommandResult(application_id=uuid4(), status_text="✅ Заявка одобрена · Test")
    markup = applicant_resolution_keyboard(result)
    assert markup is not None
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "coach_cab" in callbacks
    assert "Кабинет тренера" in labels
    assert "home" in callbacks


def test_applicant_resolution_keyboard_rejected_opens_application() -> None:
    application_id = uuid4()
    result = RejectCoachApplicationCommandResult(
        application_id=application_id,
        status_text="❌ Заявка отклонена · Test: мало опыта",
    )
    markup = applicant_resolution_keyboard(result)
    assert markup is not None
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert f"coach_app:{application_id}" in callbacks
    assert "Посмотреть заявку" in labels
    assert "home" in callbacks


def test_approved_and_rejected_keyboards_match_helpers() -> None:
    approved = coach_application_approved_keyboard()
    assert approved.inline_keyboard[0][0].callback_data == "coach_cab"

    application_id = str(uuid4())
    rejected = coach_application_rejected_keyboard(application_id=application_id)
    assert rejected.inline_keyboard[0][0].callback_data == f"coach_app:{application_id}"
