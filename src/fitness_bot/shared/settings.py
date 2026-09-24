from __future__ import annotations

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(validation_alias="BOT_TOKEN")
    database_url: str = Field(validation_alias="DATABASE_URL")
    postgres_user: str = Field(validation_alias="POSTGRES_USER")
    postgres_password: str = Field(validation_alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(validation_alias="POSTGRES_DB")
    timeweb_api_key: str = Field(validation_alias="TIMEWEB_API_KEY")
    timeweb_base_url: str = Field(validation_alias="TIMEWEB_BASE_URL")
    youtube_api_key: str = Field(validation_alias="YOUTUBE_API_KEY")
    s3_endpoint: str = Field(validation_alias="S3_ENDPOINT")
    s3_bucket: str = Field(validation_alias="S3_BUCKET")
    s3_access_key: str = Field(validation_alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(validation_alias="S3_SECRET_KEY")
    s3_region: str = Field(validation_alias="S3_REGION")
    # Empty → StubSpeechToText. Recommended path after `make download-stt-model`:
    # ./models/sherpa-onnx-zipformer-ru-2024-09-18
    sherpa_model_dir: str = Field(default="", validation_alias="SHERPA_MODEL_DIR")
    sherpa_encoder: str = Field(default="encoder.int8.onnx", validation_alias="SHERPA_ENCODER")
    sherpa_decoder: str = Field(default="decoder.int8.onnx", validation_alias="SHERPA_DECODER")
    sherpa_joiner: str = Field(default="joiner.int8.onnx", validation_alias="SHERPA_JOINER")
    sherpa_tokens: str = Field(default="tokens.txt", validation_alias="SHERPA_TOKENS")
    sherpa_num_threads: int = Field(default=2, validation_alias="SHERPA_NUM_THREADS")
    sherpa_sample_rate: int = Field(default=16_000, validation_alias="SHERPA_SAMPLE_RATE")
    # Optional one-shot seed of first moderators (numeric telegram ids), not the runtime ACL.
    bootstrap_moderator_telegram_ids: str = Field(default="", validation_alias="BOOTSTRAP_MODERATOR_TELEGRAM_IDS")

    def bootstrap_moderator_ids(self) -> frozenset[int]:
        raw = self.bootstrap_moderator_telegram_ids.strip()
        if not raw:
            return frozenset()
        values: set[int] = set()
        for part in raw.split(","):
            text = part.strip()
            if not text:
                continue
            values.add(int(text))
        return frozenset(values)


_ENV_NAMES = {
    "bot_token": "BOT_TOKEN",
    "database_url": "DATABASE_URL",
    "postgres_user": "POSTGRES_USER",
    "postgres_password": "POSTGRES_PASSWORD",
    "postgres_db": "POSTGRES_DB",
    "timeweb_api_key": "TIMEWEB_API_KEY",
    "timeweb_base_url": "TIMEWEB_BASE_URL",
    "youtube_api_key": "YOUTUBE_API_KEY",
    "s3_endpoint": "S3_ENDPOINT",
    "s3_bucket": "S3_BUCKET",
    "s3_access_key": "S3_ACCESS_KEY",
    "s3_secret_key": "S3_SECRET_KEY",
    "s3_region": "S3_REGION",
    "sherpa_model_dir": "SHERPA_MODEL_DIR",
    "sherpa_encoder": "SHERPA_ENCODER",
    "sherpa_decoder": "SHERPA_DECODER",
    "sherpa_joiner": "SHERPA_JOINER",
    "sherpa_tokens": "SHERPA_TOKENS",
    "sherpa_num_threads": "SHERPA_NUM_THREADS",
    "sherpa_sample_rate": "SHERPA_SAMPLE_RATE",
    "bootstrap_moderator_telegram_ids": "BOOTSTRAP_MODERATOR_TELEGRAM_IDS",
}


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        missing: set[str] = set()
        for error in exc.errors():
            if error["type"] != "missing":
                continue
            loc = error["loc"][0]
            missing.add(_ENV_NAMES.get(str(loc), str(loc)))
        if missing:
            names = ", ".join(sorted(missing))
            raise SystemExit(f"Missing required environment keys: {names}") from exc
        raise
