# Production image for Timeweb Cloud Apps (build context = repository root).
# Local compose still uses docker/dev/Dockerfile with volume mounts for data/models.
FROM python:3.13-slim

WORKDIR /app

# python:3.13-slim is Debian trixie. deb.debian.org crawls from Timeweb
# builders (~20 KB/s) and the apt step is killed at 1680s. mirror.yandex.ru
# serves the same trixie and trixie-security suites.
RUN sed -i 's|deb.debian.org|mirror.yandex.ru|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg bzip2 \
    && rm -rf /var/lib/apt/lists/*

# ghcr.io/astral-sh/uv crawls from Timeweb builders (~25 KB/s) and the
# 1680s buildctl limit kills the build. The same 0.12.8 wheel from PyPI is fast.
RUN pip install --no-cache-dir "uv==0.12.8"

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

# Long-polling bot + GET /health on 8080 (after alembic in entrypoint).
# Do not add HEALTHCHECK — Timeweb Apps panel probe would be overridden.
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
