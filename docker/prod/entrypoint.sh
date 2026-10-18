#!/bin/sh
set -eu

# Official k2-fsa pack. No other host publishes this exact archive.
MODEL_NAME="${SHERPA_MODEL_NAME:-sherpa-onnx-zipformer-ru-2024-09-18}"
MODEL_DIR="${SHERPA_MODEL_DIR:-/app/models/${MODEL_NAME}}"
MODEL_URL="${SHERPA_MODEL_URL:-https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${MODEL_NAME}.tar.bz2}"

model_ready() {
    [ -s "${MODEL_DIR}/tokens.txt" ] \
        && [ -s "${MODEL_DIR}/encoder.int8.onnx" ] \
        && [ -s "${MODEL_DIR}/decoder.int8.onnx" ] \
        && [ -s "${MODEL_DIR}/joiner.int8.onnx" ]
}

if [ -n "${MODEL_DIR}" ] && [ -n "${MODEL_URL}" ] && ! model_ready; then
    echo "Downloading sherpa model (~283 MB) from ${MODEL_URL}" >&2
    archive="/tmp/${MODEL_NAME}.tar.bz2"
    mkdir -p "$(dirname "${MODEL_DIR}")"
    rm -f "${archive}"
    curl -fL --retry 3 --retry-delay 2 --connect-timeout 20 \
        -o "${archive}" \
        "${MODEL_URL}" &
    curl_pid=$!
    while kill -0 "${curl_pid}" 2>/dev/null; do
        if [ -f "${archive}" ]; then
            bytes=$(wc -c < "${archive}" | tr -d ' ')
        else
            bytes=0
        fi
        echo "sherpa download ${bytes} bytes from ${MODEL_URL}" >&2
        sleep 10
    done
    if ! wait "${curl_pid}"; then
        rm -f "${archive}"
        echo "ERROR: failed to download sherpa model from ${MODEL_URL}" >&2
        exit 1
    fi
    rm -rf "${MODEL_DIR}"
    if ! tar xjf "${archive}" -C "$(dirname "${MODEL_DIR}")"; then
        rm -f "${archive}"
        echo "ERROR: failed to unpack sherpa model archive from ${MODEL_URL}" >&2
        exit 1
    fi
    rm -f "${archive}" \
        "${MODEL_DIR}/encoder.onnx" \
        "${MODEL_DIR}/decoder.onnx" \
        "${MODEL_DIR}/joiner.onnx"
    if ! model_ready; then
        echo "ERROR: sherpa archive from ${MODEL_URL} is missing tokens.txt or int8 onnx files in ${MODEL_DIR}" >&2
        exit 1
    fi
    echo "Sherpa model ready in ${MODEL_DIR}" >&2
fi

alembic upgrade head
seed-measurement-guides --offline --force
exec fitness-bot
