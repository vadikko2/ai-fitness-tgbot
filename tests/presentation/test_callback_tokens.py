from uuid import UUID, uuid4

from fitness_bot.presentation.callback_tokens import CALLBACK_DATA_LIMIT, pack_uuids, unpack_uuids
from fitness_bot.presentation.keyboards import (
    coach_history_session_keyboard,
    coach_recent_videos_keyboard,
    coach_session_history_keyboard,
)


def test_pack_uuids_roundtrip() -> None:
    left, right = uuid4(), uuid4()
    token = pack_uuids(left, right)
    assert unpack_uuids(token, 2) == (left, right)
    assert len(f"coach_hist_one:{token}") <= CALLBACK_DATA_LIMIT


def test_coach_history_callbacks_fit_telegram_limit() -> None:
    client_id = str(uuid4())
    session_id = str(uuid4())
    slot_id = str(uuid4())
    keyboards = [
        coach_session_history_keyboard(
            client_user_id=client_id,
            items=[(session_id, "Жим лёжа")],
            offset=10,
            has_more=True,
        ),
        coach_history_session_keyboard(
            client_user_id=client_id,
            watch_items=[(slot_id, "Присед")],
        ),
        coach_recent_videos_keyboard(
            client_user_id=client_id,
            items=[(slot_id, "Тяга")],
        ),
    ]
    for keyboard in keyboards:
        for row in keyboard.inline_keyboard:
            for button in row:
                assert button.callback_data is not None
                assert len(button.callback_data.encode()) <= CALLBACK_DATA_LIMIT

    packed = (
        coach_session_history_keyboard(
            client_user_id=client_id,
            items=[(session_id, "Жим")],
            offset=0,
            has_more=False,
        )
        .inline_keyboard[0][0]
        .callback_data
    )
    assert packed is not None
    token = packed.split(":", 1)[1]
    assert unpack_uuids(token, 2) == (UUID(client_id), UUID(session_id))
