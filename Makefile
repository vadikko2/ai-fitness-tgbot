COMPOSE_FILE := docker/dev/docker-compose-dev.yml
DOCKER := $(shell command -v docker 2>/dev/null || echo /Applications/Docker.app/Contents/Resources/bin/docker)
COMPOSE := $(DOCKER) compose

# Official k2-fsa Russian zipformer ASR pack (sherpa-onnx offline transducer).
SHERPA_MODEL_NAME := sherpa-onnx-zipformer-ru-2024-09-18
SHERPA_MODEL_URL := https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$(SHERPA_MODEL_NAME).tar.bz2
SHERPA_MODEL_ARCHIVE := /tmp/$(SHERPA_MODEL_NAME).tar.bz2
SHERPA_MODEL_DIR := models/$(SHERPA_MODEL_NAME)

.PHONY: dev-up dev-down pre-commit seed-catalog enrich-catalog load-catalog seed-guides download-stt-model

dev-up:
	$(COMPOSE) -f $(COMPOSE_FILE) --env-file .env up -d --build

dev-down:
	$(COMPOSE) -f $(COMPOSE_FILE) --env-file .env down

pre-commit:
	uv run pre-commit run --all-files --hook-stage pre-push --show-diff-on-failure

# C2: regenerate data/exercises.jsonl via LLM + YouTube/Rutube (needs API keys).
seed-catalog:
	uv run seed-exercise-catalog

# Rewrite technique + attach videos for existing data/exercises.jsonl (LLM + Rutube; YouTube optional).
enrich-catalog:
	uv run enrich-exercise-catalog

# Upsert existing data/exercises.jsonl into Postgres (idempotent; re-runnable).
load-catalog:
	uv run load-exercise-catalog

# C1: upsert eight fixed measurement sites + guides (offline = no LLM).
# --force refreshes instruction text from DEFAULT_MEASUREMENT_GUIDES (no site codes).
seed-guides:
	uv run seed-measurement-guides --offline --force

# Download Russian sherpa-onnx zipformer ASR into ./models (gitignored binaries).
download-stt-model:
	mkdir -p models
	@if [ -f "$(SHERPA_MODEL_DIR)/tokens.txt" ]; then \
		echo "Already present: $(SHERPA_MODEL_DIR)"; \
	else \
		curl -fL -o $(SHERPA_MODEL_ARCHIVE) $(SHERPA_MODEL_URL); \
		tar xjf $(SHERPA_MODEL_ARCHIVE) -C models; \
		rm -f $(SHERPA_MODEL_ARCHIVE); \
		echo "Unpacked to $(SHERPA_MODEL_DIR). Set SHERPA_MODEL_DIR=$(SHERPA_MODEL_DIR) in .env"; \
	fi
