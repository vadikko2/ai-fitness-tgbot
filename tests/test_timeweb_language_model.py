from __future__ import annotations

import pytest

from fitness_bot.infrastructure.adapters.language_model import (
    DEFAULT_TIMEWEB_BASE_URL,
    TimewebLanguageModel,
    normalize_openai_compatible_root,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://api.timeweb.ai/v1", "https://api.timeweb.ai/v1"),
        ("https://api.timeweb.ai/v1/", "https://api.timeweb.ai/v1"),
        (
            "https://api.timeweb.ai/v1/chat/completions",
            "https://api.timeweb.ai/v1",
        ),
        (
            "https://api.timeweb.ai/v1/chat/completions/",
            "https://api.timeweb.ai/v1",
        ),
        ("  https://api.timeweb.ai/v1/  ", "https://api.timeweb.ai/v1"),
    ],
)
def test_normalize_openai_compatible_root(raw: str, expected: str) -> None:
    assert normalize_openai_compatible_root(raw) == expected


def test_timeweb_chat_completions_url_never_doubles_path() -> None:
    lm = TimewebLanguageModel(
        api_key="test-key",
        base_url="https://api.timeweb.ai/v1/chat/completions",
    )
    assert lm.chat_completions_url == "https://api.timeweb.ai/v1/chat/completions"
    assert DEFAULT_TIMEWEB_BASE_URL == "https://api.timeweb.ai/v1"
