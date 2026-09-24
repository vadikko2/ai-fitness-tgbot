from __future__ import annotations

from pathlib import Path

import pytest


def test_load_settings_names_missing_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for key in (
        "BOT_TOKEN",
        "DATABASE_URL",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "TIMEWEB_API_KEY",
        "TIMEWEB_BASE_URL",
        "YOUTUBE_API_KEY",
        "S3_ENDPOINT",
        "S3_BUCKET",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_REGION",
        "SHERPA_MODEL_DIR",
        "SHERPA_ENCODER",
        "SHERPA_DECODER",
        "SHERPA_JOINER",
        "SHERPA_TOKENS",
        "SHERPA_NUM_THREADS",
        "SHERPA_SAMPLE_RATE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BOT_TOKEN", "x")

    from fitness_bot.shared.settings import load_settings

    with pytest.raises(SystemExit) as exc:
        load_settings()
    message = str(exc.value)
    assert "Missing required environment keys:" in message
    assert "DATABASE_URL" in message
    assert "BOT_TOKEN" not in message.split(":", 1)[1]
    assert "SHERPA_MODEL_DIR" not in message


def test_sherpa_settings_have_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for key in (
        "BOT_TOKEN",
        "DATABASE_URL",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "TIMEWEB_API_KEY",
        "TIMEWEB_BASE_URL",
        "YOUTUBE_API_KEY",
        "S3_ENDPOINT",
        "S3_BUCKET",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_REGION",
        "SHERPA_MODEL_DIR",
        "SHERPA_ENCODER",
        "SHERPA_DECODER",
        "SHERPA_JOINER",
        "SHERPA_TOKENS",
        "SHERPA_NUM_THREADS",
        "SHERPA_SAMPLE_RATE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "db")
    monkeypatch.setenv("TIMEWEB_API_KEY", "k")
    monkeypatch.setenv("TIMEWEB_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("YOUTUBE_API_KEY", "y")
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_BUCKET", "b")
    monkeypatch.setenv("S3_ACCESS_KEY", "a")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    monkeypatch.setenv("S3_REGION", "us-east-1")

    from fitness_bot.shared.settings import load_settings

    settings = load_settings()
    assert settings.sherpa_model_dir == ""
    assert settings.sherpa_encoder == "encoder.int8.onnx"
    assert settings.sherpa_decoder == "decoder.int8.onnx"
    assert settings.sherpa_joiner == "joiner.int8.onnx"
    assert settings.sherpa_tokens == "tokens.txt"
    assert settings.sherpa_num_threads == 2
    assert settings.sherpa_sample_rate == 16_000
