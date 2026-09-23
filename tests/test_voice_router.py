from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from fitness_bot.domain.enums import ExpectedInput
from fitness_bot.infrastructure.adapters.speech_to_text import FakeSpeechToText, StubSpeechToText
from fitness_bot.presentation.routers.voice import create_voice_router
from fitness_bot.service.models.queries.users import GetWorkflowQueryResult


@pytest.mark.asyncio
async def test_voice_router_stub_asks_for_text() -> None:
    from uuid import uuid4

    mediator = AsyncMock()
    mediator.send.return_value = GetWorkflowQueryResult(
        user_id=uuid4(),
        chat_id=1,
        expected_input=ExpectedInput.PROPOSAL_UTTERANCE,
        expected_field="program_edit",
        focus_slot=None,
        profile_complete=True,
        goal=None,
    )
    jinja_env = MagicMock()
    router = create_voice_router(
        jinja_env=jinja_env,
        mediator=mediator,
        speech_to_text=StubSpeechToText(),
    )
    handler = router.message.handlers[0].callback

    message = MagicMock()
    message.from_user = SimpleNamespace(id=1)
    message.voice = SimpleNamespace(file_id="fid", mime_type="audio/ogg")
    message.answer = AsyncMock()

    bot = AsyncMock()
    bot.get_file.return_value = SimpleNamespace(file_path="voice.ogg")
    download = MagicMock()
    download.read.return_value = b"ogg-bytes"
    bot.download_file.return_value = download

    await handler(message, bot)

    message.answer.assert_awaited()
    text = message.answer.await_args.args[0]
    assert "текстом" in text.lower() or "не настроено" in text.lower()


@pytest.mark.asyncio
async def test_voice_router_rejects_numeric_step() -> None:
    from uuid import uuid4

    mediator = AsyncMock()
    mediator.send.return_value = GetWorkflowQueryResult(
        user_id=uuid4(),
        chat_id=1,
        expected_input=ExpectedInput.WEIGHT,
        expected_field=None,
        focus_slot=None,
        profile_complete=True,
        goal=None,
    )
    jinja_env = MagicMock()
    fake = FakeSpeechToText(transcript="80.5")
    router = create_voice_router(
        jinja_env=jinja_env,
        mediator=mediator,
        speech_to_text=fake,
    )
    handler = router.message.handlers[0].callback

    message = MagicMock()
    message.from_user = SimpleNamespace(id=42)
    message.voice = SimpleNamespace(file_id="fid", mime_type="audio/ogg")
    message.answer = AsyncMock()
    bot = AsyncMock()

    await handler(message, bot)

    message.answer.assert_awaited()
    text = message.answer.await_args.args[0].lower()
    assert "свободный текст" in text or "цифр" in text
    assert fake.calls == []


@pytest.mark.asyncio
async def test_voice_router_fake_stt_forwards_to_utterance(monkeypatch: pytest.MonkeyPatch) -> None:
    from uuid import uuid4

    mediator = AsyncMock()
    mediator.send.return_value = GetWorkflowQueryResult(
        user_id=uuid4(),
        chat_id=1,
        expected_input=ExpectedInput.PROPOSAL_UTTERANCE,
        expected_field="program_edit",
        focus_slot=None,
        profile_complete=True,
        goal=None,
    )
    jinja_env = MagicMock()
    fake = FakeSpeechToText(transcript="добавь приседания")
    router = create_voice_router(
        jinja_env=jinja_env,
        mediator=mediator,
        speech_to_text=fake,
    )
    handler = router.message.handlers[0].callback

    called: dict[str, str] = {}

    async def fake_utterance(*, message, text, jinja_env, mediator):  # noqa: ANN001
        called["text"] = text

    monkeypatch.setattr(
        "fitness_bot.presentation.routers.voice.handle_user_utterance",
        fake_utterance,
    )

    message = MagicMock()
    message.from_user = SimpleNamespace(id=42)
    message.voice = SimpleNamespace(file_id="fid", mime_type="audio/ogg")

    bot = AsyncMock()
    bot.get_file.return_value = SimpleNamespace(file_path="voice.ogg")
    download = MagicMock()
    download.read.return_value = b"ogg-bytes"
    bot.download_file.return_value = download

    await handler(message, bot)

    assert called["text"] == "добавь приседания"
    assert fake.calls == [(b"ogg-bytes", "audio/ogg")]
