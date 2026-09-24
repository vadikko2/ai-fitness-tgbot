# ai-fitness-tgbot

Telegram fitness training bot (aiogram 3, CQRS, Postgres).

## Speech-to-text (sherpa-onnx)

Voice messages go through the `SpeechToText` port (`SherpaOnnxSpeechToText` when configured). One voice is recognized at a time. ONNX thread count comes from `SHERPA_NUM_THREADS`.

Runtime needs both `sherpa-onnx` (Python bindings) and `sherpa-onnx-core` (ships `libonnxruntime.so`). Both are listed in `pyproject.toml` because `uv` does not always pull the core package transitively from the sdist metadata.

1. Install [ffmpeg](https://ffmpeg.org/) locally (or use `docker/dev`, which installs it).
2. Download the Russian zipformer pack into `./models` (not committed — large ONNX files):

```bash
make download-stt-model
```

3. Point `.env` at the unpacked directory (see `example.env`):

```env
SHERPA_MODEL_DIR=./models/sherpa-onnx-zipformer-ru-2024-09-18
SHERPA_ENCODER=encoder.int8.onnx
SHERPA_DECODER=decoder.int8.onnx
SHERPA_JOINER=joiner.int8.onnx
SHERPA_TOKENS=tokens.txt
SHERPA_NUM_THREADS=2
SHERPA_SAMPLE_RATE=16000
```

Empty `SHERPA_MODEL_DIR` keeps a stub adapter: the bot asks for text instead of recognizing voice.
