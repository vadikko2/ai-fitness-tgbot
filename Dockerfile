# Production image for Timeweb Cloud Apps (build context = repository root).
# Local compose still uses docker/dev/Dockerfile with volume mounts for data/models.
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg bzip2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.8 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    SHERPA_MODEL_NAME=sherpa-onnx-zipformer-ru-2024-09-18 \
    SHERPA_MODEL_DIR=/app/models/sherpa-onnx-zipformer-ru-2024-09-18

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY data ./data
COPY docker/prod/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

RUN uv sync --frozen --no-dev

# Download ASR pack at build time (gitignored locally; not in the repo).
RUN mkdir -p /app/models \
    && curl -fL --retry 3 --retry-delay 2 \
        -o /tmp/sherpa.tar.bz2 \
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${SHERPA_MODEL_NAME}.tar.bz2" \
    && tar xjf /tmp/sherpa.tar.bz2 -C /app/models \
    && rm -f /tmp/sherpa.tar.bz2 \
        "/app/models/${SHERPA_MODEL_NAME}/encoder.onnx" \
        "/app/models/${SHERPA_MODEL_NAME}/decoder.onnx" \
        "/app/models/${SHERPA_MODEL_NAME}/joiner.onnx" \
    && test -f "${SHERPA_MODEL_DIR}/tokens.txt" \
    && test -f "${SHERPA_MODEL_DIR}/encoder.int8.onnx"

RUN test -d /app/data/progress_poses/male \
    && test -d /app/data/progress_poses/female

# Long-polling Telegram bot: no HTTP listener. Do not add HEALTHCHECK —
# App Platform would probe a port the process never opens.
ENTRYPOINT ["/entrypoint.sh"]
