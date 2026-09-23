from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from fitness_bot.infrastructure.adapters.speech_to_text import (
    FakeSpeechToText,
    SherpaOnnxSpeechToText,
    StubSpeechToText,
    build_speech_to_text,
)


@pytest.mark.asyncio
async def test_stub_speech_to_text_raises() -> None:
    stub = StubSpeechToText()
    with pytest.raises(NotImplementedError):
        await stub.transcribe(audio=b"x", content_type="audio/ogg")


@pytest.mark.asyncio
async def test_fake_speech_to_text_returns_transcript() -> None:
    fake = FakeSpeechToText(transcript="привет")
    text = await fake.transcribe(audio=b"ogg", content_type="audio/ogg")
    assert text == "привет"
    assert fake.calls == [(b"ogg", "audio/ogg")]


def test_build_speech_to_text_empty_dir_uses_stub() -> None:
    stt = build_speech_to_text(
        model_dir="",
        encoder="encoder.int8.onnx",
        decoder="decoder.int8.onnx",
        joiner="joiner.int8.onnx",
        tokens="tokens.txt",
        num_threads=2,
        sample_rate=16_000,
    )
    assert isinstance(stt, StubSpeechToText)


def test_build_speech_to_text_with_dir_uses_sherpa() -> None:
    stt = build_speech_to_text(
        model_dir="/tmp/models",
        encoder="encoder.int8.onnx",
        decoder="decoder.int8.onnx",
        joiner="joiner.int8.onnx",
        tokens="tokens.txt",
        num_threads=1,
        sample_rate=16_000,
    )
    assert isinstance(stt, SherpaOnnxSpeechToText)


@pytest.mark.asyncio
async def test_sherpa_transcribe_with_mocked_recognizer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    for name in ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"):
        (model_dir / name).write_bytes(b"placeholder")

    stt = SherpaOnnxSpeechToText(model_dir=model_dir, num_threads=1, sample_rate=16_000)

    stream = MagicMock()
    stream.result.text = "  вес семьдесят  "
    recognizer = MagicMock()
    recognizer.create_stream.return_value = stream

    monkeypatch.setattr(stt, "_load_recognizer", lambda: recognizer)
    monkeypatch.setattr(
        SherpaOnnxSpeechToText,
        "_audio_to_float32_mono",
        staticmethod(lambda audio, *, sample_rate: (np.zeros(1600, dtype=np.float32), sample_rate)),
    )

    text = await stt.transcribe(audio=b"fake-ogg", content_type="audio/ogg")
    assert text == "вес семьдесят"
    recognizer.decode_stream.assert_called_once_with(stream)


@pytest.mark.asyncio
async def test_sherpa_missing_model_files_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stt = SherpaOnnxSpeechToText(model_dir=tmp_path)
    monkeypatch.setattr(
        SherpaOnnxSpeechToText,
        "_audio_to_float32_mono",
        staticmethod(lambda audio, *, sample_rate: (np.zeros(10, dtype=np.float32), sample_rate)),
    )
    with pytest.raises(FileNotFoundError, match="missing"):
        await stt.transcribe(audio=b"x", content_type="audio/ogg")
