from __future__ import annotations

from fitness_bot.presentation.message_draft import assistant_parse_failure_text, draft_preview_from_partial


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
