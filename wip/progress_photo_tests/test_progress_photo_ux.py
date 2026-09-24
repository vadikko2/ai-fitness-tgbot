from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.presentation.keyboards import (
    coach_mine_keyboard,
    history_menu_keyboard,
    home_keyboard,
    progress_photo_history_keyboard,
    progress_photo_menu_keyboard,
)
from fitness_bot.presentation.routers.photo import create_photo_router
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.models.commands.body import RecordProgressPhotoCommand
from fitness_bot.service.models.queries.users import GetWorkflowQuery


def _callback_data(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_home_keyboard_ia_variant_b() -> None:
    markup = home_keyboard(has_linked_coach=False)
    callbacks = _callback_data(markup)
    assert "pp_menu" in callbacks
    assert "wt_menu" in callbacks
    assert "meas_menu" in callbacks
    assert "coach_search" in callbacks
    assert "coach_mine" not in callbacks
    assert "code_link" not in callbacks

    # Результаты shares a row with Вес and Обхваты.
    weight_row = next(row for row in markup.inline_keyboard if any(b.callback_data == "wt_menu" for b in row))
    assert [b.callback_data for b in weight_row] == ["wt_menu", "meas_menu", "pp_menu"]

    linked = home_keyboard(has_linked_coach=True)
    linked_callbacks = _callback_data(linked)
    assert "coach_mine" in linked_callbacks
    assert "coach_search" not in linked_callbacks


def test_history_and_progress_photo_menus_expose_new_callbacks() -> None:
    assert "hist_pp" in _callback_data(history_menu_keyboard())
    assert set(_callback_data(progress_photo_menu_keyboard())) >= {"pp_log", "pp_hist", "pp_remind"}
    assert "coach_mine_unlink" in _callback_data(coach_mine_keyboard())


def test_progress_photo_history_keyboard_prefixes() -> None:
    athlete = progress_photo_history_keyboard(
        items=[("set-1", "2026-09-23")],
        offset=0,
        has_more=False,
    )
    assert _callback_data(athlete) == ["pp_hist_one:set-1", "pp_menu"]

    client_id = str(uuid4())
    set_id = str(uuid4())
    coach = progress_photo_history_keyboard(
        items=[(set_id, "2026-09-20")],
        offset=10,
        has_more=True,
        subject_user_id=client_id,
        back_callback=f"coach_client:{client_id}",
    )
    callbacks = _callback_data(coach)
    assert f"coach_pp_one:{set_id}" in callbacks
    assert f"coach_pp_hist:{client_id}:0" in callbacks  # prev page
    assert f"coach_pp_hist:{client_id}:20" in callbacks  # next page
    for data in callbacks:
        assert len(data.encode("utf-8")) <= 64, data


@pytest.mark.asyncio
async def test_photo_router_routes_progress_photo() -> None:
    jinja_env = create_jinja_env()
    workflow = MagicMock()
    workflow.expected_input = ExpectedInput.PROGRESS_PHOTO
    record_result = MagicMock(complete=True, next_angle=None)
    mediator = AsyncMock()
    mediator.send = AsyncMock(side_effect=[workflow, record_result])
    storage = MagicMock()
    router = create_photo_router(jinja_env=jinja_env, mediator=mediator, object_storage=storage)
    photo_handler = router.message.handlers[0].callback

    message = MagicMock()
    message.from_user = MagicMock(id=42)
    message.photo = [MagicMock(file_id="fid")]
    message.bot = MagicMock()
    message.bot.get_file = AsyncMock(return_value=MagicMock(file_path="p.jpg"))
    buf = MagicMock()
    buf.read = MagicMock(return_value=b"img-bytes")
    message.bot.download_file = AsyncMock(return_value=buf)
    message.answer = AsyncMock()

    await photo_handler(message)

    assert isinstance(mediator.send.await_args_list[0].args[0], GetWorkflowQuery)
    record_cmd = mediator.send.await_args_list[1].args[0]
    assert isinstance(record_cmd, RecordProgressPhotoCommand)
    assert record_cmd.telegram_user_id == 42
    assert record_cmd.body == b"img-bytes"
    assert record_cmd.content_type == "image/jpeg"
    message.answer.assert_awaited()
    text = message.answer.await_args.args[0]
    assert "готов" in text.lower() or "снят" in text.lower() or "сохран" in text.lower()
