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
    SHERPA_MODEL_DIR=/app/models/sherpa-onnx-zipformer-ru-2024-09-18 \
    SHERPA_MODEL_URL=https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-ru-2024-09-18.tar.bz2

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY data ./data
COPY docker/prod/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

RUN uv sync --frozen --no-dev

# The ~283 MB sherpa archive is only published on GitHub releases. The Timeweb
# builder fetches GitHub at ~26 KB/s and is killed at 1680s, so the download
# runs in entrypoint.sh on container start instead of during docker build.

RUN test -d /app/data/progress_poses/male \
    && test -d /app/data/progress_poses/female

# Long-polling bot + GET /health on 8080 (after alembic in entrypoint).
# Do not add HEALTHCHECK — Timeweb Apps panel probe would be overridden.
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
