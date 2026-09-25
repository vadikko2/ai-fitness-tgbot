from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from fitness_bot.presentation.message_draft import (
    NUTRITION_WAITING_PHRASES,
    MessageDraftStream,
    assistant_parse_failure_text,
    draft_preview_from_partial,
)


def test_draft_preview_extracts_partial_reply() -> None:
    raw = '{"program":{"days":[]},"reply":"Собрал фуллбади на три дня'
    assert draft_preview_from_partial(raw) == "Собрал фуллбади на три дня"


def test_draft_preview_unescapes_json_string() -> None:
    raw = r'{"reply":"Раз\nдва \"три\""}'
    assert draft_preview_from_partial(raw) == 'Раз\nдва "три"'


def test_draft_preview_empty_without_reply() -> None:
    assert draft_preview_from_partial('{"program":{"days":[]}}') == ""


def test_assistant_parse_failure_merges_reply_into_one_screen() -> None:
    text = assistant_parse_failure_text("Сделал 3 дня: жимовая и тяговая.")
    assert text.startswith("Сделал 3 дня")
    assert "Не удалось разобрать ответ помощника" in text
    assert text.count("\n\n") == 1


def test_assistant_parse_failure_without_reply_is_hint_only() -> None:
    assert assistant_parse_failure_text("") == "Не удалось разобрать ответ помощника. Скажи иначе."
    assert assistant_parse_failure_text(None) == "Не удалось разобрать ответ помощника. Скажи иначе."


def test_nutrition_waiting_phrases_are_food_themed() -> None:
    assert NUTRITION_WAITING_PHRASES
    joined = " ".join(NUTRITION_WAITING_PHRASES).lower()
    assert "упражнен" not in joined
    assert any(token in joined for token in ("калор", "бжу", "режим", "норм"))


@pytest.mark.asyncio
async def test_waiting_loop_types_then_clears_before_next_phrase() -> None:
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock()
    draft = MessageDraftStream(
        bot,
        chat_id=1,
        draft_id=7,
        waiting_phrases=("Аб...", "Вг..."),
        waiting_char_delay_s=0.0,
        waiting_phrase_interval_s=0.0,
    )
    await draft.start()
    await asyncio.sleep(0.05)
    await draft.aclose()

    texts = [call.kwargs["text"] for call in bot.send_message_draft.await_args_list]
    assert texts[0] == ""
    assert "А" in texts
    assert "Аб..." in texts
    assert "" in texts[1:]  # clear between phrases
    assert draft.preview_text == ""


@pytest.mark.asyncio
async def test_model_preview_stops_waiting_and_sets_preview_text() -> None:
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock()
    draft = MessageDraftStream(
        bot,
        chat_id=1,
        draft_id=7,
        waiting_phrases=("Ждём...",),
        waiting_char_delay_s=0.0,
        waiting_phrase_interval_s=10.0,
    )
    await draft.start()
    await draft.publish_accumulated('{"reply":"Готово"}')
    await draft.aclose()
    assert draft.preview_text == "Готово"
    texts = [call.kwargs["text"] for call in bot.send_message_draft.await_args_list]
    assert texts[-1] == "Готово"
